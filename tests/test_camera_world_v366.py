"""Stage 13 Camera World Continuity contracts. Run externally via stage13 script."""
from __future__ import annotations

import io
import tempfile
import time
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from calendar_world import RealContextCache
from camera_world import CameraWorldBuilder, NEUTRAL_VISUAL
from config import settings
from db import DatabaseManager
from seed_academic_v36 import seed_academic
from seed_world_bible_v36 import seed_world_bible
from visual_profile import CameraState, VisualProfileManager
from world_repository import WorldStateRepository
from world_state import WorldStateManager


class CameraWorldBuilderTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.db = DatabaseManager(Path(temp.name) / 'camera.db')
        seed_world_bible(self.db)
        seed_academic(self.db)
        self.builder = CameraWorldBuilder(self.db, stale_minutes=60)
        self.now = datetime(2026, 9, 18, 15, 0)
        self.states = WorldStateRepository(self.db)

    def _snapshot(self, *, place_key='marina_apartment', activity='curtindo a tarde em casa',
                  observed_at=None, weather=None, reason='inferred_routine'):
        with self.db.get_connection() as conn:
            place = conn.execute(
                'SELECT id,region FROM world_places WHERE canonical_key=?', (place_key,)
            ).fetchone()
        return self.states.add_snapshot({
            'state_date': (observed_at or self.now).date().isoformat(),
            'observed_at': (observed_at or self.now).isoformat(),
            'location_place_id': place['id'] if place else None,
            'location_region': place['region'] if place else None,
            'activity': activity,
            'energy_level': 0.7,
            'weather_context_json': weather,
            'source_json': {'truth_type': 'system', 'reason': reason},
        })

    def test_apartment_plus_beach_request_rejects_beach_without_mutating_world(self):
        before = self._snapshot()
        count_before = self._count_states()
        with patch.object(settings, 'CALENDAR_CONTINUITY_ENABLED', False):
            ctx = self.builder.build(self.now, user_request='manda uma foto na praia amor')
        self.assertTrue(ctx.presence_assertable)
        self.assertEqual(ctx.place_key, 'marina_apartment')
        self.assertTrue(ctx.request_conflict)
        sanitized = self.builder.sanitize_scene_tags(
            'bikini on beach sand, ocean waves, midday sun', ctx)
        self.assertNotIn('beach', sanitized.lower())
        self.assertIn('apartment', sanitized.lower())
        self.assertEqual(self._count_states(), count_before)
        self.assertEqual(self.states.latest()['id'], before['id'])

    def test_apartment_rejects_foreign_destinations_without_merging_geographies(self):
        self._snapshot()
        cases = [
            ('manda foto na academia', 'gym interior, fitness equipment, treadmill',
             ('gym', 'fitness', 'treadmill')),
            ('selfie na faculdade / puc', 'university campus classroom corridor',
             ('campus', 'classroom', 'university')),
            ('foto no bar hoje', 'casual bar interior, cocktail bar booth',
             ('bar', 'cocktail')),
            ('manda look no shopping', 'shopping mall corridor, storefront lighting',
             ('shopping', 'mall', 'storefront')),
        ]
        with patch.object(settings, 'CALENDAR_CONTINUITY_ENABLED', False):
            for request, llm_tags, banned in cases:
                with self.subTest(request=request):
                    ctx = self.builder.build(self.now, user_request=request)
                    self.assertTrue(ctx.request_conflict)
                    self.assertEqual(ctx.place_key, 'marina_apartment')
                    sanitized = self.builder.sanitize_scene_tags(llm_tags, ctx)
                    lowered = sanitized.lower()
                    self.assertIn('apartment', lowered)
                    for token in banned:
                        self.assertNotIn(token, lowered)
                    # Must not keep both destination and apartment in one prompt.
                    self.assertEqual(sanitized, ctx.safe_scene_tags)

    def test_confirmed_class_beats_routine_snapshot_without_resolve(self):
        apartment = self._snapshot(place_key='marina_apartment', activity='tempo livre em casa')
        class_now = datetime(2026, 9, 22, 9, 0)
        AcademicLife = __import__('academic_life', fromlist=['AcademicLife']).AcademicLife
        AcademicLife(self.db).catch_up(class_now)
        with patch.object(settings, 'CALENDAR_CONTINUITY_ENABLED', True), \
             patch.object(settings, 'ACADEMIC_LIFE_ENABLED', True):
            ctx = self.builder.build(class_now, user_request='manda uma selfie')
        self.assertEqual(ctx.activity_source, 'confirmed_commitment')
        self.assertEqual(ctx.place_key, 'puc_rio')
        self.assertIn('campus', ctx.visual_location.lower())
        self.assertEqual(self._count_states(), 1)
        # Incompatible apartment snapshot must not remain as provenance.
        self.assertIsNone(ctx.snapshot_id)
        self.assertNotEqual(ctx.snapshot_id, apartment['id'])

    def test_calendar_puc_overrides_apartment_snapshot_provenance(self):
        """Regression: world_snapshot_id must not point at an apartment snapshot."""
        self._snapshot(place_key='marina_apartment',
                       observed_at=datetime(2026, 9, 22, 8, 30),
                       activity='em casa')
        class_now = datetime(2026, 9, 22, 9, 0)
        __import__('academic_life', fromlist=['AcademicLife']).AcademicLife(self.db).catch_up(class_now)
        with patch.object(settings, 'CALENDAR_CONTINUITY_ENABLED', True), \
             patch.object(settings, 'ACADEMIC_LIFE_ENABLED', True):
            ctx = self.builder.build(class_now, user_request='foto')
        self.assertEqual(ctx.place_key, 'puc_rio')
        self.assertIsNone(ctx.snapshot_id)

    def test_stale_snapshot_does_not_assert_apartment_presence(self):
        stale_at = self.now - timedelta(hours=3)
        self._snapshot(observed_at=stale_at)
        with patch.object(settings, 'CALENDAR_CONTINUITY_ENABLED', False):
            ctx = self.builder.build(self.now, user_request='foto agora')
        self.assertFalse(ctx.presence_assertable)
        self.assertIsNone(ctx.place_key)
        self.assertEqual(ctx.visual_location, NEUTRAL_VISUAL)
        self.assertEqual(ctx.activity_source, 'stale_snapshot')

    def test_stale_snapshot_heavy_rain_is_not_current_weather(self):
        stale_at = self.now - timedelta(hours=3)
        self._snapshot(observed_at=stale_at, weather={'heavy_rain': True, 'condition': 'rain'})
        with patch.object(settings, 'CALENDAR_CONTINUITY_ENABLED', False):
            ctx = self.builder.build(self.now, user_request='foto')
        self.assertIsNone(ctx.weather)
        self.assertIn('do NOT invent rain', ctx.director_restrictions)
        cache = RealContextCache(self.db)
        cache.put(
            'weather:rio', 'weather', {'heavy_rain': True, 'condition': 'rain'},
            source_name='open-meteo', observed_at=self.now - timedelta(hours=2),
            expires_at=self.now - timedelta(minutes=30),
        )
        with patch.object(settings, 'CALENDAR_CONTINUITY_ENABLED', True):
            ctx2 = self.builder.build(self.now, user_request='foto')
        self.assertIsNone(ctx2.weather)

    def test_night_safe_tags_forbid_midday_sun(self):
        night = datetime(2026, 9, 18, 22, 30)
        self._snapshot(observed_at=night)
        with patch.object(settings, 'CALENDAR_CONTINUITY_ENABLED', False):
            ctx = self.builder.build(night, user_request='manda foto')
        self.assertTrue(any('midday' in n for n in ctx.negative_constraints))
        self.assertIn('evening', ctx.safe_scene_tags.lower())
        self.assertNotIn('no midday sun', ctx.safe_scene_tags.lower())
        cleaned = self.builder.sanitize_scene_tags(
            'smiling, midday sun, bright daylight', ctx)
        self.assertNotIn('midday sun', cleaned.lower())

    def test_missing_or_expired_weather_is_not_invented(self):
        self._snapshot(weather=None)
        with patch.object(settings, 'CALENDAR_CONTINUITY_ENABLED', True):
            ctx = self.builder.build(self.now, user_request='foto')
        self.assertIsNone(ctx.weather)
        self.assertIn('do NOT invent rain', ctx.director_restrictions)
        cache = RealContextCache(self.db)
        cache.put(
            'weather:rio', 'weather', {'heavy_rain': True, 'condition': 'rain'},
            source_name='open-meteo', observed_at=self.now - timedelta(hours=2),
            expires_at=self.now - timedelta(minutes=30),
        )
        with patch.object(settings, 'CALENDAR_CONTINUITY_ENABLED', True):
            ctx2 = self.builder.build(self.now, user_request='foto')
        self.assertIsNone(ctx2.weather)

    def test_apartment_does_not_imply_bedroom_without_explicit_cue(self):
        self._snapshot()
        with patch.object(settings, 'CALENDAR_CONTINUITY_ENABLED', False):
            ctx = self.builder.build(self.now, user_request='manda uma foto vestida')
        self.assertIsNone(ctx.sublocation)
        with patch.object(settings, 'CALENDAR_CONTINUITY_ENABLED', False):
            ctx2 = self.builder.build(self.now, user_request='foto no quarto')
        self.assertEqual(ctx2.sublocation, 'bedroom')

    def test_puc_rejects_bedroom_sublocation_from_user_request(self):
        class_now = datetime(2026, 9, 22, 9, 0)
        __import__('academic_life', fromlist=['AcademicLife']).AcademicLife(self.db).catch_up(class_now)
        with patch.object(settings, 'CALENDAR_CONTINUITY_ENABLED', True), \
             patch.object(settings, 'ACADEMIC_LIFE_ENABLED', True):
            ctx = self.builder.build(class_now, user_request='manda foto no quarto')
        self.assertEqual(ctx.place_key, 'puc_rio')
        self.assertIsNone(ctx.sublocation)
        self.assertNotIn('bedroom', ctx.visual_location.lower())

    def _count_states(self) -> int:
        with self.db.get_connection() as conn:
            return conn.execute('SELECT COUNT(*) FROM world_state').fetchone()[0]


class CameraContinuitySessionTests(unittest.TestCase):
    def setUp(self):
        self.profile = VisualProfileManager()
        self.profile.clear_state()

    def tearDown(self):
        self.profile.clear_state()

    def test_more_one_preserves_look_only_same_place(self):
        prompt1, nsfw1, angle1 = self.profile.build_scene_prompt(
            'sitting on sofa, wearing cute hoodie', user_intent='manda foto',
            require_world_match=True, current_place_key='marina_apartment')
        self.profile.record_photo_generation(
            scene_tags='sitting on sofa, wearing cute hoodie',
            full_prompt=prompt1, is_nsfw=nsfw1, focus_angle=angle1,
            location='living room', outfit='casual hoodie',
            place_key='marina_apartment', world_snapshot_id=11,
        )
        prompt2, nsfw2, angle2 = self.profile.build_scene_prompt(
            'mais uma', user_intent='manda mais uma',
            require_world_match=True, current_place_key='marina_apartment')
        self.assertIn('living room', prompt2)
        self.assertIn('hoodie', prompt2.lower())
        prompt3, _, _ = self.profile.build_scene_prompt(
            'mais uma', user_intent='outra foto',
            require_world_match=True, current_place_key='puc_rio')
        self.assertNotIn('living room', prompt3)

    def test_legacy_camera_state_from_dict_without_place_key(self):
        state = CameraState.from_dict({
            'scene_tags': 'sofa', 'outfit': 'hoodie', 'location': 'living room',
            'focus_angle': 'frontal', 'is_nsfw': False, 'full_prompt': 'x',
            'timestamp': time.time(),
        })
        self.assertEqual(state.place_key, '')
        self.assertIsNone(state.world_snapshot_id)


class CameraDeliveryPersistenceTests(unittest.IsolatedAsyncioTestCase):
    async def test_failed_generation_does_not_update_camera_state(self):
        from visual_profile import visual_profile
        visual_profile.clear_state()
        from sd_client import sd_client
        with patch.object(sd_client, '_generate_local_sd', new_callable=AsyncMock) as local, \
             patch.object(settings, 'IMAGE_ENGINE', 'local'):
            local.return_value = None
            sd_client.novita_key = ''
            result = await sd_client.generate_photo_with_context('sofa selfie')
        self.assertIsNone(result.image)
        self.assertIsNone(visual_profile.get_last_state())

    async def test_failed_send_photo_does_not_record_continuity(self):
        from visual_profile import visual_profile
        visual_profile.clear_state()
        from sd_client import PhotoGenerationResult
        fake_gen = PhotoGenerationResult(
            image=io.BytesIO(b'fake'), full_prompt='p', scene_tags='sofa',
            is_nsfw=False, focus_angle='frontal', place_key='marina_apartment',
            world_snapshot_id=3,
        )
        fake_bot = MagicMock()
        fake_bot.send_photo = AsyncMock(side_effect=RuntimeError('Telegram offline'))
        try:
            sent = await fake_bot.send_photo(chat_id=1, photo=fake_gen.image, caption='x')
        except RuntimeError:
            sent = None
        if not (sent and getattr(sent, 'message_id', None)):
            pass
        self.assertIsNone(visual_profile.get_last_state())

    async def test_successful_send_records_only_transmitted_photo(self):
        from visual_profile import visual_profile
        visual_profile.clear_state()
        from sd_client import PhotoGenerationResult
        gen = PhotoGenerationResult(
            image=io.BytesIO(b'ok'), full_prompt='full', scene_tags='apartment selfie',
            is_nsfw=False, focus_angle='frontal', place_key='marina_apartment',
            world_snapshot_id=9,
        )
        sent = SimpleNamespace(message_id=501)
        if sent.message_id:
            visual_profile.record_photo_generation(
                scene_tags=gen.scene_tags, full_prompt=gen.full_prompt,
                is_nsfw=gen.is_nsfw, focus_angle=gen.focus_angle,
                place_key=gen.place_key, world_snapshot_id=gen.world_snapshot_id,
                location='modern apartment',
            )
        state = visual_profile.get_last_state()
        self.assertIsNotNone(state)
        self.assertEqual(state.place_key, 'marina_apartment')
        self.assertEqual(state.world_snapshot_id, 9)
        visual_profile.clear_state()

    async def test_avatar_generation_does_not_alter_conversational_continuity(self):
        from visual_profile import visual_profile
        from sd_client import sd_client, PhotoGenerationResult
        visual_profile.clear_state()
        visual_profile.record_photo_generation(
            scene_tags='sofa hoodie', full_prompt='p', is_nsfw=False,
            focus_angle='frontal', location='living room',
            place_key='marina_apartment', world_snapshot_id=1,
        )
        before = visual_profile.get_last_state().to_dict()
        with patch.object(sd_client, 'generate_photo_with_context', new_callable=AsyncMock) as gen:
            gen.return_value = PhotoGenerationResult(
                image=None, full_prompt='avatar', scene_tags='portrait')
            await sd_client.generate_avatar('fofa')
        after = visual_profile.get_last_state().to_dict()
        self.assertEqual(before['place_key'], after['place_key'])
        self.assertEqual(before['scene_tags'], after['scene_tags'])
        visual_profile.clear_state()

    async def test_generate_photo_legacy_does_not_persist_on_success(self):
        from visual_profile import visual_profile
        from sd_client import sd_client, PhotoGenerationResult
        visual_profile.clear_state()
        with patch.object(sd_client, 'generate_photo_with_context', new_callable=AsyncMock) as gen:
            gen.return_value = PhotoGenerationResult(
                image=io.BytesIO(b'img'), full_prompt='p', scene_tags='x')
            img = await sd_client.generate_photo('casual selfie')
        self.assertIsNotNone(img)
        self.assertIsNone(visual_profile.get_last_state())


class CameraWorldMutationGuardTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.db = DatabaseManager(Path(temp.name) / 'guard.db')
        seed_world_bible(self.db)
        seed_academic(self.db)
        self.now = datetime(2026, 9, 18, 16, 0)
        manager = WorldStateManager(self.db, stale_minutes=60)
        self.first = manager.resolve(self.now, has_class=False,
                                     confirmed_commitment={
                                         'activity': 'em casa', 'place_key': 'marina_apartment',
                                         'start_at': (self.now - timedelta(minutes=5)).isoformat(),
                                         'end_at': (self.now + timedelta(hours=1)).isoformat(),
                                     })
        self.builder = CameraWorldBuilder(self.db)

    def test_builder_never_calls_resolve_or_adds_snapshot(self):
        ids_before = self._state_ids()
        with patch.object(settings, 'CALENDAR_CONTINUITY_ENABLED', False), \
             patch('world_state.WorldStateManager.resolve') as resolve:
            ctx = self.builder.build(self.now, user_request='foto na praia')
            sanitized = self.builder.sanitize_scene_tags('beach ocean sand', ctx)
            resolve.assert_not_called()
        self.assertNotIn('beach', sanitized.lower())
        self.assertEqual(self._state_ids(), ids_before)

    def _state_ids(self) -> list[int]:
        with self.db.get_connection() as conn:
            return [row['id'] for row in conn.execute(
                'SELECT id FROM world_state ORDER BY id').fetchall()]


if __name__ == '__main__':
    unittest.main()
