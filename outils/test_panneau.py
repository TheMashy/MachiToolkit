# -*- coding: utf-8 -*-
"""
LE PANNEAU MONTRE CE QUE LA GUIRLANDE MONTRE -- A SA CADENCE, A SON ECLAT.

Demande : « fixer un bug ou la lumiere affichee n'est pas accurate (trop sombre
par rapport a ce que les leds m'affichent reellement, ce qui est la bonne
intensite) ; adapter le taux de rafraichissement reel set pour les leds pour ce
graphique, le montrer a la place des guirlandes ; page minimaliste, fond sombre
gris bleu, petites etoiles jaunes dans les menus, une option = une icone ».

Tenu ici :
  - la couleur peinte est celle que la LED EMET (sa valeur est une lumiere
    lineaire ; l'ecran applique une courbe) : 24 envoye se peint 86, pas 24 ;
  - chaque image fixee par la boucle Bluetooth est notee ; le graphe en dessine
    une colonne chacune, et la cadence tenue se mesure sur leurs instants ;
  - une icone par page, les etoiles jamais sur une icone, la page ouverte a la
    sienne.

    python outils/test_panneau.py          (la partie a l'ecran : sous X, ou xvfb-run)
"""
import importlib.util
import os
import sys
import tempfile
import time
import unittest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def charger_module(dossier):
    os.environ["LOCALAPPDATA"] = dossier
    spec = importlib.util.spec_from_file_location("mt_panneau", os.path.join(RACINE, "machi_tool.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


M = charger_module(tempfile.mkdtemp())

try:
    import tkinter
    tkinter.Tk().destroy()
    ECRAN = True
except Exception:
    ECRAN = False


class CeQueLaLedEmet(unittest.TestCase):
    def test_la_valeur_envoyee_est_une_lumiere_lineaire(self):
        # Le cas de la capture : #180806 envoye. L'ecran le montrait presque noir.
        self.assertEqual(M.vu_a_l_oeil((24, 8, 6)), (86, 50, 42))
        self.assertEqual(M.vu_a_l_oeil((0, 0, 0)), (0, 0, 0))
        self.assertEqual(M.vu_a_l_oeil((255, 255, 255)), (255, 255, 255))
        # Toujours plus clair qu'envoye, jamais moins (sauf aux bornes).
        for v in range(1, 255):
            self.assertGreaterEqual(M.vu_a_l_oeil((v, v, v))[0], v)
        prec = -1
        for v in range(256):
            vu = M.vu_a_l_oeil((v, 0, 0))[0]
            self.assertGreaterEqual(vu, prec)
            prec = vu

    def test_l_eclat(self):
        self.assertEqual(M.eclat((0, 0, 0)), 0.0)
        self.assertAlmostEqual(M.eclat((255, 255, 255)), 1.0, places=6)
        self.assertGreater(M.eclat((0, 255, 0)), M.eclat((0, 0, 255)), "le vert eclaire plus que le bleu")
        self.assertGreater(M.eclat((24, 8, 6)), 0.2, "une LED a 9 % se voit, elle n'est pas noire")


class LaCadenceReelle(unittest.TestCase):
    def setUp(self):
        M.IMAGES_LED.clear()

    def test_chaque_image_est_notee_dans_l_ordre(self):
        depart = M._IMAGES_N[0]
        for i in range(5):
            M.noter_image_led((i, i, i), instant=100.0 + i)
        nouvelles = M.images_depuis(depart + 2)
        self.assertEqual([im[2] for im in nouvelles], [(2, 2, 2), (3, 3, 3), (4, 4, 4)])
        self.assertEqual(M.images_depuis(M._IMAGES_N[0]), [])

    def test_la_cadence_se_mesure_sur_les_instants(self):
        for i in range(61):
            M.noter_image_led((10, 10, 10), instant=1000.0 + i / 30.0)
        self.assertAlmostEqual(M.cadence_reelle(2.0, maintenant=1002.0), 30.0, delta=1.0)
        self.assertEqual(M.cadence_reelle(2.0, maintenant=1010.0), 0.0, "plus rien ne part : 0")

    def test_la_boucle_note_chaque_image_qu_elle_fixe(self):
        with open(os.path.join(RACINE, "machi_tool.py"), encoding="utf-8") as f:
            src = f.read()
        corps = src[src.index("async def une_session"):src.index("async def superviseur")]
        i = corps.index('ETAT["couleur"] = envoi')
        self.assertIn("noter_image_led(envoi)", corps[i:i + 400])


@unittest.skipUnless(ECRAN, "pas d'ecran (lancer sous xvfb-run)")
class AL_Ecran(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        M.DOSSIER = tempfile.mkdtemp()
        M.CFG.clear()
        M.CFG.update(M.charger_config())
        M.ETAT.update(connecte=True, couleur=(24, 8, 6))
        cls.p = M.Panneau(M.CFG, lambda: None)
        cls.p.root.update()

    @classmethod
    def tearDownClass(cls):
        cls.p.root.destroy()

    def test_le_graphe_une_colonne_par_image(self):
        p = self.p
        M.IMAGES_LED.clear()
        p.redessiner_graphe(800)
        for i in range(40):
            M.noter_image_led((24 + i, 8, 6))
        p.avancer_graphe()
        self.assertEqual(len(p.graphe_barres), 40)
        derniere = p.graphe.itemcget(p.graphe_barres[-1], "fill")
        self.assertEqual(derniere, M.rgb_vers_hex(M.vu_a_l_oeil((63, 8, 6))))
        # Au fil de l'eau (le cas normal, un tour de panneau = quelques images) :
        # chaque image a sa colonne, aucune sautee.
        for i in range(7):
            M.noter_image_led((100, 10 * i, 6))
        p.avancer_graphe()
        self.assertEqual(len(p.graphe_barres), 47)
        couleurs = [p.graphe.itemcget(b, "fill") for b in list(p.graphe_barres)[-7:]]
        self.assertEqual(couleurs, [M.rgb_vers_hex(M.vu_a_l_oeil((100, 10 * i, 6))) for i in range(7)])
        # Les colonnes restent collees : pas de trou ni de chevauchement.
        xs = [p.graphe.coords(b)[0] for b in p.graphe_barres]
        self.assertTrue(all(abs((b - a) - p.px(M.GRAPHE_PAS)) < 0.01 for a, b in zip(xs, xs[1:])))
        # Plus d'images que de place, par petits paquets : on garde les plus
        # recentes, pas une de plus -- dans la file ET dans la toile.
        capacite = (800 - 2 * p.px(18)) // p.px(M.GRAPHE_PAS)
        for _ in range(capacite // 20 + 3):
            for i in range(20):
                M.noter_image_led((200, 90, 20))
            p.avancer_graphe()
        self.assertEqual(len(p.graphe_barres), capacite)
        self.assertEqual(len(p.graphe.find_withtag("barre")), capacite, "pas d'objet oublie dans la toile")
        # Et d'un coup, plus que toute la largeur : on redessine depuis l'historique.
        for i in range(2000):
            M.noter_image_led((200, 90, 20))
        p.avancer_graphe()
        self.assertEqual(len(p.graphe.find_withtag("barre")), capacite)

    def test_sans_guirlande_le_panneau_s_anime_quand_meme(self):
        """Machi Tool ouvert, guirlande pas encore connectee : aucune image. Une
        exception ici arreterait l'animation pour de bon (Tk ne rappelle plus)."""
        M.IMAGES_LED.clear()
        p = M.Panneau(M.CFG, lambda: None)
        try:
            p.cadence_vue = 0.0
            p.avancer_graphe()
            self.assertEqual(p.graphe.itemcget(p.graphe_absent, "text"), "la guirlande ne recoit rien")
        finally:
            p.root.destroy()

    def test_une_icone_par_page_et_l_etoile_de_la_page_ouverte(self):
        p = self.p
        self.assertEqual(set(p.onglets), {cle for cle, _, _, _ in M.MENU})
        p.aller("jarvis")
        for cle, (_, _, marque, _) in p.onglets.items():
            self.assertEqual(p.rail_toile.itemcget(marque, "state"),
                             "normal" if cle == "jarvis" else "hidden", cle)

    def test_les_etoiles_ne_touchent_aucune_icone(self):
        p = self.p
        p.semer_etoiles(p.px(M.RAIL_LARGEUR), p.px(700))
        self.assertGreater(len(p.etoiles), 8)
        cx = p.px(M.RAIL_LARGEUR) / 2.0
        for item, _ in p.etoiles:
            x0, y0, x1, y1 = p.rail_toile.bbox(item)
            x, y = (x0 + x1) / 2.0, (y0 + y1) / 2.0
            for _, _, _, yc in p.onglets.values():
                self.assertGreater(((x - cx) ** 2 + (y - yc) ** 2) ** 0.5, p.px(18))

    def test_le_fond_est_gris_bleu(self):
        r, v, b = M.hex_vers_rgb(M.NUIT)
        self.assertGreater(b, r)
        self.assertLess(max(r, v, b), 48, "sombre")


if __name__ == "__main__":
    unittest.main(verbosity=1)
