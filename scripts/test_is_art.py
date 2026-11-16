import io
import unittest
from PIL import Image
from sync_is_art import candidates, cg_ids, convert, icon_ids, size_limit, ART, AVG, CC, UI

class IsArtTests(unittest.TestCase):
    def test_global_sprite_replaces_the_same_cn_path_and_cn_only_remains(self):
        def item(name, sha): return {'path': ART + '/itempic/' + name + '.png', 'type': 'blob', 'sha': sha}
        snapshots = {'cn': {'commit': 'c' * 40, 'tree': [item('shared', 'cn'), item('future', 'future')]}, 'en': {'commit': 'e' * 40, 'tree': [item('shared', 'en')]}}
        result = candidates(snapshots, {'shared', 'future'})
        self.assertEqual(result['content-art/integrated-strategies/itempic/shared.webp']['sourceRegion'], 'en')
        self.assertEqual(result['content-art/integrated-strategies/itempic/future.webp']['sourceRegion'], 'cn')

    def test_native_ids_not_translated_display_names_select_squad_and_mechanic_art(self):
        data = {'name': 'Not an asset ID', 'iconId': 'rogue_3_band_1', 'mechanics': [{'iconId': 'pic_rogue_3_chaos_1'}]}
        entries = [{'path': UI + '/rogue_3/init/initreliciconpic/rogue_3_band_1.png', 'type': 'blob', 'sha': 'a'}, {'path': UI + '/rogue_3/misc/not_an_icon.png', 'type': 'blob', 'sha': 'b'}]
        result = candidates({'cn': {'commit': 'c' * 40, 'tree': entries}, 'en': {'commit': 'e' * 40, 'tree': []}}, icon_ids(data))
        self.assertEqual(len(result), 1)
        self.assertIn('content-art/integrated-strategies/topics/rogue_3/init/initreliciconpic/rogue_3_band_1.webp', result)

    def test_small_native_icons_are_not_upscaled_and_transparency_survives(self):
        image = Image.new('RGBA', (64, 32), (0, 0, 0, 0)); image.putpixel((20, 20), (255, 0, 0, 255))
        buf = io.BytesIO(); image.save(buf, 'PNG')
        content, size = convert(buf.getvalue())
        self.assertEqual(size, (64, 32))
        self.assertEqual(Image.open(io.BytesIO(content)).getpixel((0, 0))[3], 0)

    def test_coins_endings_key_art_and_contract_art_are_selected_by_native_id(self):
        table = {'details': {'rogue_5': {'endings': {'e1': {'id': 'e1', 'bgId': 'pic_rogue_5_47'}}}}, 'modules': {'rogue_5': {'copper': {'copperData': {'x_a': {'groupId': 'rogue_5_copper_B_01'}, 'other': {'groupId': 'rogue_5_nextlevel_1'}}}}}}
        self.assertEqual(icon_ids(table), {'rogue_5_copper_b_01'})
        self.assertEqual(cg_ids(table), {'pic_rogue_5_47'})
        def blob(path): return {'path': path, 'type': 'blob', 'sha': path}
        tree = [blob(ART + '/itempic/rogue_5_copper_b_01.png'), blob(AVG + '/pic_rogue_5_47.png'), blob(AVG + '/unrelated_story.png'),
                blob(UI + '/rogue_5_update/entrykeyvisuals/rogue_kv_default/bg.png'), blob(CC + '/runeicon/g_char_atk_1.png'), blob(CC + '/shopback/normal_common.png')]
        result = candidates({'cn': {'commit': 'c' * 40, 'tree': tree}, 'en': {'commit': 'e' * 40, 'tree': tree[:1]}}, icon_ids(table), cg_ids(table))
        self.assertEqual(sorted(result), [
            'content-art/contingency-contract/runeicon/g_char_atk_1.webp',
            'content-art/integrated-strategies/cg/pic_rogue_5_47.webp',
            'content-art/integrated-strategies/itempic/rogue_5_copper_b_01.webp',
            'content-art/integrated-strategies/topics/rogue_5_update/entrykeyvisuals/rogue_kv_default/bg.webp'])
        self.assertEqual(result['content-art/integrated-strategies/itempic/rogue_5_copper_b_01.webp']['sourceRegion'], 'en')
        self.assertEqual(size_limit('content-art/integrated-strategies/topics/rogue_5_update/entrykeyvisuals/rogue_kv_default/bg.webp'), 1600)
        self.assertEqual(size_limit('content-art/integrated-strategies/cg/pic_rogue_5_47.webp'), 1280)
        self.assertEqual(size_limit('content-art/contingency-contract/runeicon/g_char_atk_1.webp'), 192)

if __name__ == '__main__': unittest.main()
