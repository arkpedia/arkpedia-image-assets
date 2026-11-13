import io
import unittest
from PIL import Image
from sync_is_art import candidates, convert, icon_ids, ART, UI

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

if __name__ == '__main__': unittest.main()
