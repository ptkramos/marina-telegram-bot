"""Fotos pelo Civitai (24/09) — rede simulada; a suíte nunca gasta Buzz."""
import asyncio
import unittest
from unittest.mock import patch

from types import SimpleNamespace

import civitai_images as ci


class _Resp:
    def __init__(self, status=200, json_data=None, body=b"", ctype="application/json"):
        self.status, self._json, self._body, self.headers = status, json_data, body, {"Content-Type": ctype}

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def json(self):
        return self._json

    async def text(self):
        return str(self._json)

    async def read(self):
        return self._body


class _Session:
    def __init__(self, blob_ok=True):
        self.calls, self.polls, self.blob_ok = [], 0, blob_ok

    def post(self, url, headers=None, json=None):
        self.calls.append(("POST", url, json))
        return _Resp(json_data={"id": "wf1", "status": "processing", "cost": {"total": 10}})

    def get(self, url, headers=None, allow_redirects=True):
        self.calls.append(("GET", url, headers))
        if "/workflows/" in url:
            self.polls += 1
            done = self.polls >= 2
            return _Resp(json_data={"id": "wf1", "status": "succeeded" if done else "processing",
                                    "steps": [{"output": {"images": [{"id": "blob9", "url": "https://signed/x.jpg",
                                                                      "available": True}]}}]})
        if "/blobs/blob9" in url:
            return _Resp(body=b"JPEGDATA", ctype="image/jpeg") if self.blob_ok else _Resp(status=403, ctype="text/html")
        return _Resp(body=b"SIGNED", ctype="image/jpeg")


class CivitaiTest(unittest.TestCase):
    def setUp(self):
        # Configuração falsa e isolada: a suíte recarrega `config`, e patchear o
        # settings global deixava a chave REAL vazar pro teste (e pro log).
        self.fake = SimpleNamespace(CIVITAI_API_KEY="tok", IPHONE_LORAS_ENABLED=True)
        for p in (patch.object(ci, "ALLOW_LIVE_IN_TESTS", True), patch.object(ci, "POLL_S", 0.0),
                  patch.object(ci, "_settings", return_value=self.fake)):
            p.start()
            self.addCleanup(p.stop)

    def test_same_lora_pipeline_as_the_novita_workflow(self):
        sfw = ci.select_loras(is_nsfw=False)
        self.assertEqual(sfw[ci.LORAS["marina"]], 1.0)
        self.assertEqual(sfw[ci.LORAS["iphone_photo"]], 0.6)
        self.assertIn(ci.LORAS["hands"], sfw)
        self.assertNotIn(ci.LORAS["nsfw_master"], sfw)
        adult = ci.select_loras(is_nsfw=True, focus_angle="behind", is_mirror_selfie=True)
        self.assertEqual(adult[ci.LORAS["nsfw_master"]], 0.8)
        self.assertEqual(adult[ci.LORAS["roundass"]], 0.65)
        self.assertIn(ci.LORAS["mirror_selfie"], adult)
        self.assertNotIn(ci.LORAS["hands"], adult)

    def test_adult_photo_asks_for_mature_content_and_yellow_buzz(self):
        body = ci.build_workflow("p", {}, is_nsfw=True)
        self.assertTrue(body["allowMatureContent"])
        self.assertEqual(body["currencies"], ["yellow"])
        step = body["steps"][0]["input"]
        self.assertEqual((step["engine"], step["ecosystem"], step["width"], step["height"], step["steps"]),
                         ("comfy", "flux1", 832, 1216, 24))
        self.assertNotIn("currencies", ci.build_workflow("p", {}, is_nsfw=False))

    def test_generate_polls_and_downloads_through_the_authenticated_blob(self):
        s = _Session()
        img = asyncio.run(ci.generate("marina selfie", is_nsfw=True, session=s))
        self.assertEqual(img.getvalue(), b"JPEGDATA")
        blob_call = next(c for c in s.calls if "/blobs/blob9" in c[1])
        self.assertTrue(blob_call[2]["Authorization"] == "Bearer tok", "usa o token (sem imprimir o valor)")

    def test_signed_url_is_the_fallback(self):
        img = asyncio.run(ci.generate("marina selfie", is_nsfw=False, session=_Session(blob_ok=False)))
        self.assertEqual(img.getvalue(), b"SIGNED")

    def test_without_token_nothing_is_sent(self):
        self.fake.CIVITAI_API_KEY = ""
        if True:
            s = _Session()
            self.assertIsNone(asyncio.run(ci.generate("x", is_nsfw=False, session=s)))
            self.assertEqual(s.calls, [])


class Krea2Test(unittest.TestCase):
    """Pipeline Krea 2 (24/09): só liga com o LoRA Krea 2 da Marina."""

    def setUp(self):
        self.fake = SimpleNamespace(CIVITAI_API_KEY="tok", CIVITAI_ECOSYSTEM="krea2",
                                    CIVITAI_LORA_MARINA_KREA2="urn:air:krea2:lora:civitai:1@2", CIVITAI_BREAST_SLIDER=1.5)
        p = patch.object(ci, "_settings", return_value=self.fake)
        p.start()
        self.addCleanup(p.stop)

    def test_without_her_krea2_lora_it_stays_on_flux(self):
        self.fake.CIVITAI_LORA_MARINA_KREA2 = ""
        self.assertEqual(ci.ecosystem(), "flux1")

    def test_normal_photo_uses_official_turbo_and_no_adult_loras(self):
        body = ci.build_workflow_krea2("p", is_nsfw=False)
        step = body["steps"][0]["input"]
        self.assertEqual((step["ecosystem"], step["model"], step["steps"], step["cfgScale"]), ("krea2", "turbo", 8, 1))
        self.assertNotIn("diffusionModel", step)
        self.assertEqual(step["loras"]["urn:air:krea2:lora:civitai:1@2"], 1.0)
        self.assertEqual(step["loras"][ci.KREA2_BREAST_SLIDER], 1.5)
        self.assertFalse(set(ci.KREA2_ADULT) & set(step["loras"]))
        self.assertFalse(body["allowMatureContent"])

    def test_adult_photo_uses_the_uncensored_checkpoint_and_yellow_buzz(self):
        body = ci.build_workflow_krea2("p", is_nsfw=True)
        step = body["steps"][0]["input"]
        self.assertEqual(step["diffusionModel"], ci.KREA2_AIO)
        self.assertTrue(set(ci.KREA2_ADULT) <= set(step["loras"]))
        self.assertEqual(body["currencies"], ["yellow"])


if __name__ == "__main__":
    unittest.main()
