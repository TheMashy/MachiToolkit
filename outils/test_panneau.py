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

    def test_la_boule_s_affiche_sans_planter(self):
        """Sa boule a l'ecran : une couleur mal passee la faisait planter a
        chaque image, et elle n'est jamais apparue."""
        p = self.p
        vieux = {k: M.CFG.get(k) for k in ("jarvis_actif", "jarvis_boule", "jarvis_panneau")}
        etat = M.JARVIS.get("etat")
        try:
            M.CFG.update(jarvis_actif=True, jarvis_boule=True, jarvis_panneau=False)
            for e in ("ecoute", "parle"):
                M.JARVIS["etat"] = e
                self.assertEqual(p._boule_tic(), 40, e)
                p.root.update()
                self.assertEqual(p.boule.state(), "normal", e)
                self.assertGreaterEqual(len(p.boule_toile.find_all()), 4)
            M.JARVIS["etat"] = "attente"
            for _ in range(12):
                p._boule_tic()
            self.assertEqual(p.boule.state(), "withdrawn", "elle s'efface quand il se tait")
        finally:
            M.CFG.update(vieux)
            M.JARVIS["etat"] = etat

    def test_la_fenetre_relit_les_reglages_changes_ailleurs(self):
        """Revue : un journal d'activite coupe par Jarvis se rallumait au premier
        « Enregistrer », la fenetre reecrivant ses vieilles cases."""
        p = self.p
        garde = {k: M.CFG.get(k) for k in ("collecte_active", "collecte_envoi", "jarvis_panneau", "mode",
                                           "jarvis_appellation", "ecran_source")}
        try:
            p.var_act.set(1)
            M.CFG.update(collecte_active=False, jarvis_panneau=True, mode="son", jarvis_appellation="Capitaine")
            p.relire_reglages({"collecte_active", "jarvis_panneau", "mode", "jarvis_appellation", "cle_inconnue"})
            self.assertEqual(p.var_act.get(), 0)
            self.assertEqual(p.vars_jarvis["jarvis_panneau"].get(), 1)
            self.assertEqual(p.var_mode.get(), "son")
            self.assertEqual(p.champ_appellation.get(), "Capitaine")
            # une source d'ecran qui n'est ni « actif » ni un numero ne fait pas
            # planter « Enregistrer »
            p.var_source.set("n'importe quoi")
            p.enregistrer()
            self.assertEqual(M.CFG["ecran_source"], "actif")
        finally:
            M.CFG.update(garde)

    def test_chaque_case_enregistree_se_relit(self):
        """Toute variable que `enregistrer` recopie dans la config doit pouvoir
        etre remise d'accord par relire_reglages -- sinon Jarvis la change, et
        « Enregistrer » la remet a l'ancienne valeur."""
        import re
        src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "machi_tool.py"),
                   encoding="utf-8").read()
        corps = src[src.index("    def enregistrer(self):"):]
        corps = corps[:corps.index("\n    def ", 10)]
        paires = re.findall(r'self\.cfg\["(\w+)"\] = [^\n]*?self\.(var_\w+)\.get\(\)', corps)
        self.assertGreater(len(paires), 30)
        for cle, var in paires:
            trouvee = M.Panneau.VARIABLES_REGLAGES.get(cle, "var_" + cle)
            self.assertEqual(trouvee, var, cle)
        for cle, champ in re.findall(r'self\.cfg\["(\w+)"\] = [^\n]*?self\.(champ_\w+)\.get\(\)', corps):
            if cle in M._jv.REGLAGES_INTERDITS:
                continue                  # jamais change par Jarvis
            self.assertEqual(M.Panneau.CHAMPS_REGLAGES.get(cle), champ, cle)

    def test_la_boule_seule_et_sa_legende(self):
        """« Jarvis ne devrait afficher que la petite bulle, plus la grande
        fenetre, le texte peut s'afficher en minuscule a cote (ecran 4K) » : pas
        de panneau, la boule dans chaque etat, et a cote d'elle, en petit, ce
        qu'il dit -- du cote de l'ecran ou il y a la place."""
        p = self.p
        cles = ("jarvis_actif", "jarvis_boule", "jarvis_panneau", "jarvis_legende", "jarvis_boule_x")
        vieux = {k: M.CFG.get(k) for k in cles}
        garde = {k: M.JARVIS.get(k) for k in ("etat", "sous_titre", "regard", "entendu", "fait_jusqua")}
        try:
            M.CFG.update(jarvis_actif=True, jarvis_boule=True, jarvis_panneau=M.CONFIG_DEFAUT["jarvis_panneau"],
                         jarvis_legende=True, jarvis_boule_x=0.97)
            M.JARVIS.update(regard=None, entendu="mets du jazz", sous_titre=None, fait_jusqua=0.0)
            self.assertEqual(p._panneau_tic(), 500, "le grand panneau ne s'ouvre plus")
            M.JARVIS["etat"] = "pense"
            self.assertEqual(p._boule_tic(), 40, "la boule seule sort aussi quand il reflechit")
            p.root.update()
            self.assertEqual(p.legende.state(), "normal")
            self.assertEqual(p.legende_texte.cget("text"), "\u00ab mets du jazz \u00bb")
            # il parle : la legende suit sa voix, a GAUCHE d'une boule rangee a droite
            M.JARVIS["etat"] = "parle"
            t0 = time.time() - 30
            M.JARVIS["sous_titre"] = {"phrases": ["Voici du jazz, Monsieur."], "k": 0, "t0": t0, "duree": 1.0}
            p._boule_tic()
            p.root.update()
            self.assertEqual(p.legende_texte.cget("text"), "Voici du jazz, Monsieur.")
            self.assertLessEqual(p.legende.winfo_x() + p.legende.winfo_width(), p.boule.winfo_x(),
                                 "a gauche de la boule")
            # une boule rangee a gauche : la legende passe a droite
            M.CFG["jarvis_boule_x"] = 0.02
            for _ in range(40):
                p._boule_tic()
            p.root.update()
            self.assertGreaterEqual(p.legende.winfo_x(), p.boule.winfo_x() + p.boule.winfo_width())
            # une commande faite : la boule le montre un instant, puis s'efface avec sa legende
            M.JARVIS.update(etat="attente", sous_titre=None, entendu="", fait_jusqua=time.time() + 5)
            p._boule_tic()
            p.root.update()
            self.assertEqual(p.legende_texte.cget("text"), M._jv.MOTS_LEGENDE[M.langue_jarvis(M.CFG)]["fait"])
            M.JARVIS["fait_jusqua"] = 0.0
            for _ in range(12):
                p._boule_tic()
            p.root.update()
            self.assertEqual(p.boule.state(), "withdrawn")
            self.assertEqual(p.legende.state(), "withdrawn", "la legende part avec elle")
            # decochee : la boule, sans texte
            M.CFG["jarvis_legende"] = False
            M.JARVIS["etat"] = "pense"
            p._boule_tic()
            p.root.update()
            self.assertEqual(p.legende.state(), "withdrawn")
        finally:
            M.CFG.update(vieux)
            M.JARVIS.update(garde)

    def test_la_boule_joue_avec_sa_voix_meme_avec_le_panneau(self):
        """« Un petit peu de jazz » : avec son panneau, elle ne sortait plus que
        pour regarder un ecran. Elle sort quand il parle et quand il ecoute, et
        ses touches suivent l'enveloppe de sa voix -- jamais sur un jeu."""
        p = self.p
        vieux = {k: M.CFG.get(k) for k in ("jarvis_actif", "jarvis_boule", "jarvis_panneau")}
        garde = {k: M.JARVIS.get(k) for k in ("etat", "sous_titre", "regard")}
        plein = M.plein_ecran_occupe
        try:
            M.CFG.update(jarvis_actif=True, jarvis_boule=True, jarvis_panneau=True)
            M.JARVIS.update(regard=None)
            for e in ("ecoute", "parle"):
                M.JARVIS["etat"] = e
                self.assertEqual(p._boule_tic(), 40, e)
                p.root.update()
                self.assertEqual(p.boule.state(), "normal", "avec le panneau aussi : " + e)
            M.JARVIS["etat"] = "pense"
            for _ in range(12):
                p._boule_tic()
            self.assertEqual(p.boule.state(), "withdrawn", "avec le panneau, pas quand il reflechit")
            # ses touches suivent sa voix ; les objets sont deplaces, pas refaits
            M.JARVIS["etat"] = "parle"

            def touche_la_plus_haute(niveau):
                t0 = time.time() - M._jv.VOIX_LATENCE_S - 0.5
                M.JARVIS["sous_titre"] = {"phrases": ["Bien."], "k": 0, "t0": t0, "duree": 2.0,
                                          "enveloppe": (t0, 0.05, [niveau] * 40)}
                self.assertEqual(p._boule_tic(), 40)
                return max(abs(p.boule_toile.coords(o)[3] - p.boule_toile.coords(o)[1])
                           for o in p.boule_objets["touches"])
            objets = p.boule_toile.find_all()
            muet, fort = touche_la_plus_haute(0), touche_la_plus_haute(99)
            self.assertGreater(fort, muet + 4, "sa voix enfonce les touches")
            self.assertEqual(p.boule_toile.find_all(), objets, "pas de delete('all') a chaque image")
            self.assertGreaterEqual(len(objets), 4)
            # la voix de Windows ne dit rien de son son : elle swingue quand meme
            M.JARVIS["sous_titre"] = {"phrases": ["Oui."], "k": -1, "estime": True, "t0": time.time()}
            self.assertEqual(p._boule_tic(), 40)
            # UN JEU EN PLEIN ECRAN : elle se cache
            M.plein_ecran_occupe = lambda *a: True
            self.assertEqual(p._boule_tic(), 500)
            p.root.update()
            self.assertEqual(p.boule.state(), "withdrawn", "jamais par-dessus un jeu")
        finally:
            M.plein_ecran_occupe = plein
            M.CFG.update(vieux)
            M.JARVIS.update(garde)

    def test_une_seule_boucle_de_boule_apres_refaire_interface(self):
        """Un changement d'ecran refait l'interface : l'ancienne boucle de la
        boule doit s'arreter, sinon elles s'additionnent."""
        p = M.Panneau(M.CFG, lambda: None)
        try:
            appels = []
            p._panneau_tic = lambda: 100
            p._boule_tic = lambda: appels.append(time.time()) or 100

            def tourner(s):
                fin = time.time() + s
                while time.time() < fin:
                    p.root.update()
                    time.sleep(0.005)
            tourner(0.8)                                   # la boucle tourne deja...
            for _ in range(2):
                p.refaire_interface(p.echelle)             # ... quand l'ecran change, deux fois
                tourner(0.8)
            del appels[:]
            tourner(1.0)
            # une boucle : ~10 tours par seconde ; trois : ~30
            self.assertLessEqual(len(appels), 14, len(appels))
            self.assertGreaterEqual(len(appels), 5, "elle tourne toujours")
        finally:
            for a in p.root.tk.splitlist(p.root.tk.call("after", "info")):
                p.root.after_cancel(a)
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


    def test_l_agenda_se_modifie_et_se_vide_a_la_main(self):
        """« Rajoute une interface pour le faire directement a la main via
        l'agenda » : chaque rendez-vous se clique, dans toutes les vues (la
        frise comprise) ; en modification, « Retirer » et « Annuler » sont la."""
        vrais = (M.retirer_agenda, M.sauver_config)
        self.addCleanup(lambda: (setattr(M, "retirer_agenda", vrais[0]), setattr(M, "sauver_config", vrais[1])))
        M.sauver_config = lambda cfg: True
        retires = []
        M.retirer_agenda = lambda cfg, ident: (retires.append(ident), {"texte": "Retire."})[1]
        auj = time.strftime("%Y-%m-%d")
        rdv = [{"id": 11, "date": auj, "heure": "18:00", "label": "Kine-temoin"},
               {"id": 12, "date": M._jv.plus_jours(auj, 1), "heure": "10:15", "label": "Dentiste-temoin"},
               {"id": 13, "date": M._jv.plus_jours(auj, 1), "fin": M._jv.plus_jours(auj, 4), "label": "Vacances-temoin"}]
        p = M.Panneau(M.CFG, lambda: None)
        try:
            p.remplir_agenda = lambda discret=False: None        # pas de BrainDebugger ici
            p.ouvrir_agenda()
            p.root.update()
            self.assertIn("clic sur un rendez-vous", p.agenda_tete.cget("text"))
            for mode in ("frise", "liste", "semaine", "mois"):
                vue = M._jv.bornes_vue(mode, auj) if mode in ("semaine", "mois") else None
                p._agenda_mode(mode)
                p._agenda_recu({"etat": "ok", "rdv": [dict(r) for r in rdv], "bilan": M.bilan_local(auj),
                                "aujourdhui": auj, "message": "", "vue": vue, "rdv_vue": [dict(r) for r in rdv]})
                p.root.update()
                cliquables = [z for z in p._agenda_zones if "_agenda_menu" in z[4].__code__.co_names]
                self.assertGreaterEqual(len(cliquables), 3, "%s : chaque rendez-vous se clique" % mode)
            p._agenda_editer(rdv[1])
            p.root.update()
            self.assertEqual((p.agenda_bouton_retirer.winfo_manager(), p.agenda_bouton_annuler.winfo_manager()),
                             ("pack", "pack"), "en modification : « Retirer » et « Annuler » sont poses")
            self.assertIn("DENTISTE-TEMOIN", p.agenda_tete.cget("text"))
            p.agenda_bouton_annuler.invoke()
            p.root.update()
            self.assertEqual(p.agenda_bouton_retirer.winfo_manager(), "", "annule : le formulaire redevient « ajouter »")
            p._agenda_editer(rdv[1])
            p.agenda_bouton_retirer.invoke()
            for _ in range(50):
                if retires:
                    break
                time.sleep(0.02)
            self.assertEqual(retires, [12])
        finally:
            p.root.destroy()


    def test_la_bulle_de_claude_code_sur_la_page(self):
        """« Une bulle de statut quand Claude reflechit » : la case, et le bouton
        qui branche Claude Code (ses reglages, ici un fichier jetable)."""
        vrais = (M.sauver_config, M.reglages_claude_code)
        self.addCleanup(lambda: (setattr(M, "sauver_config", vrais[0]), setattr(M, "reglages_claude_code", vrais[1])))
        M.sauver_config = lambda cfg: True
        dossier = tempfile.mkdtemp()
        chemin = os.path.join(dossier, ".claude", "settings.json")
        M.reglages_claude_code = lambda: chemin
        p = M.Panneau(M.CFG, lambda: None)
        try:
            p.aller("panneau")
            p.root.update()
            self.assertEqual(p.var_panneau_claude.get(), 1)
            # « une notification en attente sur Discord » : sa case aussi
            M.PANNEAU["discord"] = 2
            p.var_panneau_discord.set(0)
            p.regler_panneau("panneau_discord")
            self.assertFalse(M.CFG["panneau_discord"])
            self.assertIsNone(M.PANNEAU["discord"], "decochee : la pastille s'en va tout de suite")
            M.CFG["panneau_discord"] = True
            # « il ne la detecte pas » : ce qu'il lit, source par source, sous la case
            self.assertIn("cinq secondes", p.txt_discord.cget("text"))
            garde = M._DISCORD.get("lisible")
            M._DISCORD["lisible"] = "Lu a 12:00:00 : la pastille montre 1."
            p._peindre_panneau()
            M._DISCORD["lisible"] = garde
            self.assertEqual(p.txt_discord.cget("text"), "Lu a 12:00:00 : la pastille montre 1.")
            # « un effet sur le panneau lorsqu'une maj est en cours » : sa case
            p.var_panneau_maj.set(0)
            p.regler_panneau("panneau_maj")
            self.assertFalse(M.CFG["panneau_maj"])
            M.CFG["panneau_maj"] = True
            # « detecter quand je vais sur FL Studio » : sa case, et la vue s'en va tout de suite
            self.assertEqual(p.var_panneau_fl.get(), 1)
            M.PANNEAU["fl"] = {"depuis": 0.0, "vu": 0.0, "projet": ""}
            p.var_panneau_fl.set(0)
            p.regler_panneau("panneau_fl")
            self.assertFalse(M.CFG["panneau_fl"])
            self.assertIsNone(M.PANNEAU["fl"])
            M.CFG["panneau_fl"] = True
            p.var_panneau_claude.set(0)
            p.regler_panneau("panneau_claude")
            self.assertFalse(M.CFG["panneau_claude"])
            self.assertEqual(p.bouton_claude_code.cget("text"), "Brancher Claude Code")
            p.basculer_claude_code()
            self.assertTrue(M.claude_code_branche(chemin))
            self.assertEqual(p.bouton_claude_code.cget("text"), "Debrancher Claude Code")
            self.assertIn("Ajoute", p.txt_claude_code.cget("text"))
            p.basculer_claude_code()
            self.assertFalse(M.claude_code_branche(chemin))
            # les sessions cloud : la variable a copier (hors de Windows, elle s'affiche)
            garde = M.CFG.get("pont_cle")
            M.CFG["pont_cle"] = "cle-de-test"
            p.copier_cle_bulle()
            M.CFG["pont_cle"] = garde
            self.assertEqual(p.txt_claude_cloud.cget("text"), "MACHITOOL_BULLE_CLE=bbb1f950f42614c413242a554340eaac")
        finally:
            M.CFG["panneau_claude"] = True
            p.root.destroy()

    def test_le_micro_choisi_garde_son_nom(self):
        """« Jarvis n'est plus detecte » : le micro choisi est retenu avec son
        nom (l'oreille le retrouve s'il change d'identifiant), et la liste suit
        l'identifiant que l'oreille a retrouve."""
        vrais = (M.sauver_config, M.liste_micros, M.envoyer_oreille)
        sauve = {k: M.CFG.get(k) for k in ("jarvis_micro", "jarvis_micro_nom")}
        self.addCleanup(lambda: (setattr(M, "sauver_config", vrais[0]), setattr(M, "liste_micros", vrais[1]),
                                 setattr(M, "envoyer_oreille", vrais[2]), M.CFG.update(sauve)))
        M.sauver_config = lambda cfg: True
        M.envoyer_oreille = lambda c: True
        M.liste_micros = lambda: [("{A}", "Microphone (Blue Yeti)"), ("{B}", "Webcam")]
        M.CFG.update(jarvis_micro="", jarvis_micro_nom="")
        p = M.Panneau(M.CFG, lambda: None)
        try:
            p.aller("jarvis")
            p.root.update()
            p.var_jarvis_micro.set("{A}")
            self.assertEqual((M.CFG["jarvis_micro"], M.CFG["jarvis_micro_nom"]), ("{A}", "Microphone (Blue Yeti)"))
            p.var_jarvis_micro.set("")
            self.assertEqual((M.CFG["jarvis_micro"], M.CFG["jarvis_micro_nom"]), ("", ""), "celui de Windows")
            p.var_jarvis_micro.set("{B}")
            # l'oreille le retrouve sous un autre identifiant : la liste le montre coche
            M.liste_micros = lambda: [("{A}", "Microphone (Blue Yeti)"), ("{B2}", "Webcam")]
            M.CFG["jarvis_micro"] = "{B2}"
            p.remplir_micros()
            self.assertEqual(p.var_jarvis_micro.get(), "{B2}")
            self.assertEqual(M.CFG["jarvis_micro_nom"], "Webcam", "son nom reste")
        finally:
            p.root.destroy()

    def test_le_cycle_se_regle_sur_la_page_du_panneau(self):
        """« Rajoute tout ca en settings dans le tab panel » : les reglettes et
        les cases du cycle ecrivent la config, le panneau les suit."""
        vrai = M.sauver_config
        self.addCleanup(lambda: setattr(M, "sauver_config", vrai))
        M.sauver_config = lambda cfg: True
        p = M.Panneau(M.CFG, lambda: None)
        try:
            p.aller("panneau")
            p.root.update()
            self.assertEqual(int(p.var_panneau_cycle_duree.get()), 30)
            self.assertAlmostEqual(float(p.var_panneau_cycle_fondu.get()), 3.0)
            p.var_panneau_cycle_duree.set(45)
            p.var_panneau_cycle_fondu.set(5.5)
            self.assertEqual((M.CFG["panneau_cycle_duree"], M.CFG["panneau_cycle_fondu"]), (45, 5.5))
            self.assertEqual(M.reglages_cycle(M.CFG), (45.0, 5.5))
            p.var_panneau_cycle_meteo.set(0)
            p.regler_panneau("panneau_cycle_meteo")
            self.assertFalse(M.CFG["panneau_cycle_meteo"])
            p.var_panneau_cycle_saut.set(0)
            p.regler_panneau("panneau_cycle_saut")
            self.assertFalse(M.CFG["panneau_cycle_saut"])
            # « un petit :3 » se decoche, la sensibilite de l'egaliseur se regle
            p.var_panneau_cycle_chat.set(0)
            p.regler_panneau("panneau_cycle_chat")
            self.assertFalse(M.CFG["panneau_cycle_chat"])
            # « un petit chat en maid » aussi
            p.var_panneau_cycle_maid.set(0)
            p.regler_panneau("panneau_cycle_maid")
            self.assertFalse(M.CFG["panneau_cycle_maid"])
            # « quand des notes ne sont pas encore posees sur des journees » : sa case
            self.assertEqual(p.var_panneau_cycle_notes.get(), 1)
            p.var_panneau_cycle_notes.set(0)
            p.regler_panneau("panneau_cycle_notes")
            self.assertFalse(M.CFG["panneau_cycle_notes"])
            # « des effets de transition prenant tout le panneau, comme des screen savers » : la case,
            # le rythme, la duree, et « Montrer un ecran »
            self.assertEqual(p.var_panneau_ecrans.get(), 1)
            p.var_panneau_ecrans.set(0)
            p.regler_panneau("panneau_ecrans")
            self.assertFalse(M.CFG["panneau_ecrans"])
            p.var_panneau_ecrans_intervalle.set(12)
            p.var_panneau_ecrans_duree.set(30)
            self.assertEqual((M.CFG["panneau_ecrans_intervalle"], M.CFG["panneau_ecrans_duree"]), (12, 30))
            self.assertEqual(M.reglages_ecrans(M.CFG), (720.0, 30.0))
            M.PANNEAU.pop("ecran_demande", None)
            p.montrer_ecran()
            self.assertTrue(M.PANNEAU.pop("ecran_demande"))
            # lesquels : une case par ecran, « Tous », « Les ambiances seulement »
            self.assertEqual(set(p.vars_ecrans), set(M.ECRANS))
            p.vars_ecrans["matrice"].set(0)
            p.choisir_ecrans()
            self.assertEqual(M.CFG["panneau_ecrans_sans"], ["matrice"])
            p.choisir_ecrans(list(M.ECRANS_AMBIANCES))
            self.assertEqual(M.ecrans_permis(M.CFG), list(M.ECRANS_AMBIANCES))
            p.choisir_ecrans(list(M.ECRANS))
            self.assertEqual(M.CFG["panneau_ecrans_sans"], [])
            self.assertAlmostEqual(float(p.var_panneau_eq_sensibilite.get()), 1.0)
            p.var_panneau_eq_sensibilite.set(1.8)
            self.assertEqual(M.CFG["panneau_eq_sensibilite"], 1.8)
        finally:
            for cle in ("panneau_cycle_duree", "panneau_cycle_fondu", "panneau_cycle_meteo", "panneau_cycle_saut",
                        "panneau_cycle_chat", "panneau_cycle_maid", "panneau_cycle_notes", "panneau_eq_sensibilite",
                        "panneau_ecrans", "panneau_ecrans_intervalle", "panneau_ecrans_duree",
                        "panneau_ecrans_sans"):
                M.CFG[cle] = M.CONFIG_DEFAUT[cle]
            p.root.destroy()


if __name__ == "__main__":
    unittest.main(verbosity=1)
