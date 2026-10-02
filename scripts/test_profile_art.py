import io
import unittest
from PIL import Image
from sync_profile_art import UI_SPRITES, convert, icon_jobs, jobs, portrait_jobs, portrait_name, ui_jobs


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
                {'path': '[uc]nc_moon_1/skin_style/name_card_short.png', 'sha': 'f', 'type': 'blob'},
                {'path': '[uc]nc_avemujica_1/skin_style/name_card_short_2.png', 'sha': 'g', 'type': 'blob'},
                {'path': '[uc]nc_avemujica_1/skin_style/name_card_long_2.png', 'sha': 'h', 'type': 'blob'},
                {'path': '[uc]nc_rhodes_light/skin_style/short.png', 'sha': 'i', 'type': 'blob'},
            ],
            'medalicon': [{'path': 'act10rune/medal_activity_10rune_035.png', 'sha': 'e', 'type': 'blob'}],
        }
        self.assertEqual([job[0] for job in jobs(listing)], [
            'profile-avatars/avatar_special_41.webp',
            'profile-namecards/nc_moon_1-bg.webp',
            'profile-namecards/nc_moon_1-strip.webp',
            'profile-namecards/nc_moon_1-head.webp',
            'profile-namecards/nc_avemujica_1-head-2.webp',
            'profile-namecards/nc_avemujica_1-strip-2.webp',
            'profile-namecards/nc_rhodes_light-head.webp',
            'profile-medals/medal_activity_10rune_035.webp',
        ])

    def test_the_cards_sprites_are_published_under_their_own_names(self):
        listing = {folder: [{'path': path, 'sha': path, 'type': 'blob'} for path in paths] for folder, paths in UI_SPRITES.items()}
        listing['namecardv2'].append({'path': 'sub_skin_change_view/back_mask.png', 'sha': 'x', 'type': 'blob'})
        targets = {job[0]: job[1] for job in ui_jobs(listing)}
        self.assertEqual(len(targets), sum(len(paths) for paths in UI_SPRITES.values()))
        self.assertEqual(targets['profile-ui/level_bg.webp'], 'assets/dyn/ui/[uc]namecardv2/prefabs/module_avatar_simple/level_bg.png')
        self.assertEqual(targets['profile-ui/elite_2.webp'], 'assets/dyn/arts/elite_hub/elite_2.png')
        self.assertNotIn('profile-ui/back_mask.webp', targets)
        self.assertEqual(targets['profile-ui/operator_collect_bg.webp'], 'assets/dyn/ui/[uc]namecardv2/prefabs/module_collect/operator_collect_bg.png')

    def test_module_marks_and_skill_icons_are_published_under_the_games_ids(self):
        listing = {
            'profile-modules': [{'path': 'arc-y.png', 'sha': 'a', 'type': 'blob'}, {'path': 'AMB-X.png', 'sha': 'b', 'type': 'blob'}],
            'profile-skills': [{'path': 'skill_icon_skchr_ascln_2.png', 'sha': 'c', 'type': 'blob'}, {'path': 'notes.txt', 'sha': 'd', 'type': 'blob'},
                               {'path': 'skill_icon_skcom_enchant[1].png', 'sha': 'e', 'type': 'blob'}],
        }
        jobs = {job[0]: (job[1], job[3]) for job in icon_jobs(listing)}
        self.assertEqual(jobs, {
            'profile-modules/arc-y.webp': ('assets/dyn/arts/ui/uniequipdirection/arc-y.png', 'icon'),
            'profile-modules/amb-x.webp': ('assets/dyn/arts/ui/uniequipdirection/AMB-X.png', 'icon'),
            'profile-skills/skchr_ascln_2.webp': ('assets/dyn/arts/skills/skill_icon_skchr_ascln_2.png', 'skill'),
            # A shared icon, named with its index as a suffix: no brackets in a URL.
            'profile-skills/skcom_enchant_1.webp': ('assets/dyn/arts/skills/skill_icon_skcom_enchant[1].png', 'skill'),
        })

    def test_a_sprite_the_dump_moved_fails_the_run(self):
        listing = {folder: [{'path': path, 'sha': path, 'type': 'blob'} for path in paths if 'level_bg' not in path] for folder, paths in UI_SPRITES.items()}
        with self.assertRaisesRegex(ValueError, 'level_bg'):
            list(ui_jobs(listing))

    def test_an_outfits_portrait_is_named_by_its_skin_id(self):
        # The page names a portrait from the account's skin id; the dump files it by a stem.
        self.assertEqual(portrait_name('char_1013_chen2@boc#6'), portrait_name('char_1013_chen2_boc#6'))
        self.assertEqual(portrait_name('char_1013_chen2#2'), 'char_1013_chen2_2')
        self.assertEqual(portrait_name('char_002_amiya#1+'), 'char_002_amiya_1p')
        listing = [
            {'path': 'skins', 'sha': 't', 'type': 'tree'},
            {'path': 'char_003_kalts_boc#6.png', 'sha': 'low', 'type': 'blob'},
            {'path': 'skins/char_003_kalts_boc#6.png', 'sha': 'high', 'type': 'blob'},
            {'path': 'linkages/char_456_ash_rainbow6#1.png', 'sha': 'ash', 'type': 'blob'},
            {'path': 'char_002_amiya_1+.png', 'sha': 'amiya', 'type': 'blob'},
            {'path': 'roguelike/char_504_rguard_1.png', 'sha': 'r', 'type': 'blob'},
            {'path': 'sp_char_124_kroos_sale#14.png', 'sha': 'sp', 'type': 'blob'},
        ]
        self.assertEqual([(job[0], job[2]) for job in portrait_jobs(listing)], [
            ('profile-portraits/char_002_amiya_1p.webp', 'amiya'),
            ('profile-portraits/char_003_kalts_boc_6.webp', 'high'),
            ('profile-portraits/char_456_ash_rainbow6_1.webp', 'ash'),
        ])

    def test_art_is_sized_for_the_page(self):
        self.assertEqual(convert(png((1920, 1080), 'RGB'), 'bg')[1], (1280, 720))
        self.assertEqual(convert(png((159, 180)), 'medal')[1], (85, 96))
        self.assertEqual(convert(png((150, 150)), 'avatar')[1], (150, 150))
        self.assertEqual(convert(png((84, 84)), 'ui')[1], (84, 84))
        with Image.open(io.BytesIO(convert(png((150, 150)), 'avatar')[0])) as image:
            self.assertEqual((image.format, image.mode), ('WEBP', 'RGBA'))


if __name__ == '__main__':
    unittest.main()
