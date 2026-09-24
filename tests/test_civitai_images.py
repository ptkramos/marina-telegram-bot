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
                                    CIVITAI_LORA_MARINA_KREA2="urn:air:krea2:lora:civitai:1@2", CIVITAI_BREAST_SLIDER=1.5,
                                    CIVITAI_KREA2_SFW_STACK="n1", CIVITAI_KREA2_NSFW_STACK="a")
        p = patch.object(ci, "_settings", return_value=self.fake)
        p.start()
        self.addCleanup(p.stop)

    def test_without_her_krea2_lora_it_stays_on_flux(self):
        self.fake.CIVITAI_LORA_MARINA_KREA2 = ""
        self.assertEqual(ci.ecosystem(), "flux1")

    def test_normal_photo_n1_uses_official_turbo_and_guards_against_nudity(self):
        body = ci.build_workflow_krea2("p", is_nsfw=False)
        step = body["steps"][0]["input"]
        self.assertEqual((step["ecosystem"], step["model"], step["steps"], step["cfgScale"]), ("krea2", "turbo", 8, 1))
        self.assertNotIn("diffusionModel", step, "base escolhida pelo Patrick: Turbo oficial")
        self.assertEqual(step["loras"]["urn:air:krea2:lora:civitai:1@2"], 1.0)
        self.assertEqual(step["loras"][ci.KREA2_BREAST_SLIDER], 1.5)
        self.assertEqual(step["loras"][ci.KREA2_NSFW_HELPER], ci.KREA2_SFW_GUARD)
        self.assertIn(ci.KREA2_EMOTIONS, step["loras"])
        self.assertNotIn(ci.KREA2_SNOFS, step["loras"])
        self.assertEqual((step["loras"][ci.KREA2_LENOVO], step["loras"][ci.KREA2_REALISM_ENGINE]), (1.0, 0.8),
                         "pilha escolhida pelo Patrick")
        self.assertNotIn(ci.KREA2_NICEGIRLS, step["loras"])
        self.assertFalse(body["allowMatureContent"])
        self.assertNotIn("currencies", body)

    def test_lenovo_only_on_selfies(self):
        selfie = ci.build_workflow_krea2("a close-up selfie", is_nsfw=False)["steps"][0]["input"]["loras"]
        far = ci.build_workflow_krea2("her whole body in the frame, not a selfie", is_nsfw=False)["steps"][0]["input"]["loras"]
        self.assertIn(ci.KREA2_LENOVO, selfie)
        self.assertNotIn(ci.KREA2_LENOVO, far)
        self.assertIn(ci.KREA2_REALISM_ENGINE, far)
        self.assertEqual(far["urn:air:krea2:lora:civitai:1@2"], ci.MARINA_WEIGHT_DISTANT)
        self.assertEqual(selfie["urn:air:krea2:lora:civitai:1@2"], 1.0)

    def test_normal_photo_n2_uses_stable_yogi_and_snapshot(self):
        self.fake.CIVITAI_KREA2_SFW_STACK = "n2"
        step = ci.build_workflow_krea2("p", is_nsfw=False)["steps"][0]["input"]
        self.assertEqual(step["diffusionModel"], ci.KREA2_YOGI)
        self.assertIn(ci.KREA2_SNAPSHOT, step["loras"])
        self.assertNotIn(ci.KREA2_LENOVO, step["loras"])

    def test_adult_stacks(self):
        a = ci.build_workflow_krea2("p", is_nsfw=True)
        step = a["steps"][0]["input"]
        self.assertNotIn("diffusionModel", step)   # A: Turbo oficial + SNOFS, sem outros modelos NSFW
        self.assertEqual(step["loras"][ci.KREA2_SNOFS], 1.0)
        self.assertEqual(step["loras"][ci.KREA2_NSFW_HELPER], 0.5)
        self.assertEqual(step["loras"][ci.KREA2_BREAST_SLIDER], 1.5, "mesmo corpo da foto vestida")
        self.assertEqual(a["currencies"], ["yellow"])
        self.assertTrue(a["allowMatureContent"])
        b = ci.build_workflow_krea2("p", is_nsfw=True, stack="b")["steps"][0]["input"]
        self.assertEqual((b["diffusionModel"], b["steps"]), (ci.KREA2_AIO, 12))
        self.assertNotIn(ci.KREA2_SNOFS, b["loras"])
        c = ci.build_workflow_krea2("p", is_nsfw=True, stack="c")["steps"][0]["input"]
        self.assertEqual(c["diffusionModel"], ci.KREA2_YOGI)
        self.assertEqual(c["loras"][ci.KREA2_REALISM_ENGINE], 0.7)
        d = ci.build_workflow_krea2("p", is_nsfw=True, stack="d")["steps"][0]["input"]
        self.assertNotIn("diffusionModel", d)
        self.assertEqual(d["loras"][ci.KREA2_NSFW_V4], 1.0)

    def test_fineporn_stack_has_nothing_nsfw_on_top(self):
        e = ci.build_workflow_krea2("p", is_nsfw=True, stack="e")["steps"][0]["input"]
        self.assertEqual((e["diffusionModel"], e["steps"], e["scheduler"]), (ci.KREA2_FINEPORN, 10, "beta"))
        self.assertFalse({ci.KREA2_SNOFS, ci.KREA2_NSFW_HELPER} & set(e["loras"]))
        self.assertEqual(e["loras"][ci.KREA2_PHONE], 0.8)
        self.assertEqual(e["loras"][ci.KREA2_TANLINES], 0.6, "marquinha só na foto adulta")
        n3 = ci.build_workflow_krea2("p", is_nsfw=False, stack="n3")["steps"][0]["input"]
        self.assertNotIn(ci.KREA2_TANLINES, n3["loras"])
        self.assertEqual(e["loras"][ci.KREA2_BREAST_SLIDER], 1.5)

    def test_a_normal_stack_name_never_serves_an_adult_photo(self):
        self.fake.CIVITAI_KREA2_NSFW_STACK = "n1"
        self.assertEqual(ci.krea2_stack_name(is_nsfw=True), "e")
        self.fake.CIVITAI_KREA2_SFW_STACK = "c"
        self.assertEqual(ci.krea2_stack_name(is_nsfw=False), "n3")

    def test_occasion_loras_follow_the_scene(self):
        grab = ci.build_workflow_krea2("She is naked, squeezing her breasts with both hands", is_nsfw=True, stack="e")
        inp = grab["steps"][0]["input"]
        self.assertEqual(inp["loras"][ci.KREA2_SQUEEZE], 0.6)
        self.assertIn("Squeezing breasts, her nipples stay small and delicate.", inp["prompt"],
                      "gatilho do LoRA + mamilo pequeno entram no prompt")
        wet = ci.build_workflow_krea2("right after the shower, wet hair", is_nsfw=False, stack="n3")["steps"][0]["input"]
        self.assertIn(ci.KREA2_WETNESS, wet["loras"])
        self.assertNotIn(ci.KREA2_SQUEEZE, wet["loras"])
        plain = ci.build_workflow_krea2("sitting on the couch", is_nsfw=True, stack="e")["steps"][0]["input"]
        self.assertFalse({ci.KREA2_SQUEEZE, ci.KREA2_WETNESS} & set(plain["loras"]))
        sfw_grab = ci.build_workflow_krea2("holding her breasts", is_nsfw=False, stack="n3")["steps"][0]["input"]
        self.assertNotIn(ci.KREA2_SQUEEZE, sfw_grab["loras"], "LoRA de apertar os seios só na foto adulta")

    def test_phone_slider_on_every_photo_and_colors_are_corrected(self):
        for nsfw, stack in ((False, "n3"), (True, "e")):
            for text in ("a close-up selfie", "whole body, not a selfie"):
                loras = ci.build_workflow_krea2(text, is_nsfw=nsfw, stack=stack)["steps"][0]["input"]["loras"]
                self.assertEqual(loras[ci.KREA2_PHONE], 0.8, (stack, text))
        import io as _io
        from PIL import Image
        buf = _io.BytesIO()
        Image.new("RGB", (8, 8), (255, 0, 0)).save(buf, format="JPEG")
        out = Image.open(_io.BytesIO(ci._desaturate(buf.getvalue(), 0.5))).getpixel((4, 4))
        self.assertLess(out[0] - out[1], 200, "menos saturada")


class Krea2PromptTest(unittest.TestCase):
    def test_natural_language_with_her_trigger_and_traits(self):
        import visual_profile as vp
        p = vp.krea2_prompt("sitting on the couch, wearing pajamas, photorealistic, 8k", is_nsfw=False)
        self.assertTrue(p.startswith("marinaX, Detailed Emotions and Expressions."))
        self.assertIn("amber-hazel eyes", p)
        self.assertIn("golden blonde tips", p)
        self.assertIn("fully clothed", p)
        self.assertNotIn("photorealistic", p.lower())
        self.assertNotIn("8k", p)
        self.assertNotIn("naked", p)

    def test_distant_scene_is_not_a_selfie(self):
        import visual_profile as vp
        p = vp.krea2_prompt("A full body photo standing on a sidewalk, the camera a few meters away", is_nsfw=False)
        self.assertIn("full body photo of", p)
        self.assertTrue(p.startswith("Full body shot"), "enquadramento primeiro")
        self.assertIn("not a selfie", p)
        self.assertNotIn("iPhone photo", p)
        close = vp.krea2_prompt("A close-up selfie on the couch", is_nsfw=False)
        self.assertIn("smartphone photo", close)
        self.assertNotIn("not a selfie", close)

    def test_adult_prompt_follows_the_angle(self):
        import visual_profile as vp
        p = vp.krea2_prompt("bathroom", is_nsfw=True, focus_angle="behind", is_mirror=True)
        self.assertIn("Seen from behind", p)
        self.assertIn("bikini tan-lines", p, "gatilho da marquinha na foto adulta")
        self.assertNotIn("tan-lines", vp.krea2_prompt("couch", is_nsfw=False))
        self.assertIn("no moles or dots", p, "corpo canônico: sem pinta (Patrick, 24/09)")
        self.assertIn(vp.KREA2_BODY_CANON, vp.krea2_prompt("bed", is_nsfw=True))
        self.assertNotIn("areolas", vp.krea2_prompt("bed", is_nsfw=False))
        self.assertIn("mirror selfie", p)
        self.assertIn("unblemished skin", p)


if __name__ == "__main__":
    unittest.main()
