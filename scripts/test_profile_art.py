import io
import unittest
from PIL import Image
from sync_profile_art import convert, jobs


def png(size, mode='RGBA'):
    out = io.BytesIO()
    image = Image.new(mode, size, (200, 40, 40, 255) if mode == 'RGBA' else (200, 40, 40))
    if mode == 'RGBA':
        image.putpixel((0, 0), (0, 0, 0, 0))  # transparent, as the game's avatars and medals are
    image.save(out, 'PNG')
    return out.getvalue()


class ProfileArtTests(unittest.TestCase):
    def test_each_file_is_published_under_the_games_id(self):
        listing = {
            'playeravatar': [{'path': 'avatar_special_41.png', 'sha': 'a', 'type': 'blob'}, {'path': 'notes.txt', 'sha': 'x', 'type': 'blob'}],
            'namecardskin': [
                {'path': '[uc]nc_moon_1', 'sha': 't', 'type': 'tree'},
                {'path': '[uc]nc_moon_1/skin_style/bg.png', 'sha': 'b', 'type': 'blob'},
                {'path': '[uc]nc_moon_1/skin_style/name_card_long.png', 'sha': 'c', 'type': 'blob'},
                {'path': '[uc]nc_moon_1/skin_style/sdk.png', 'sha': 'd', 'type': 'blob'},
            ],
            'medalicon': [{'path': 'act10rune/medal_activity_10rune_035.png', 'sha': 'e', 'type': 'blob'}],
        }
        self.assertEqual([job[0] for job in jobs(listing)], [
            'profile-avatars/avatar_special_41.webp',
            'profile-namecards/nc_moon_1-bg.webp',
            'profile-namecards/nc_moon_1-strip.webp',
            'profile-medals/medal_activity_10rune_035.webp',
        ])

    def test_art_is_sized_for_the_page(self):
        self.assertEqual(convert(png((1920, 1080), 'RGB'), 'bg')[1], (1280, 720))
        self.assertEqual(convert(png((159, 180)), 'medal')[1], (85, 96))
        self.assertEqual(convert(png((150, 150)), 'avatar')[1], (150, 150))
        with Image.open(io.BytesIO(convert(png((150, 150)), 'avatar')[0])) as image:
            self.assertEqual((image.format, image.mode), ('WEBP', 'RGBA'))


if __name__ == '__main__':
    unittest.main()
