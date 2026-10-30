// lot_eau_ciel.h -- les ecrans de ce lot, portes de machi_tool.py (croquis v10).
#pragma once

// humeurs : 0 = tropical, 1 = nuit
struct E_recif { char rien; };
void s_recif(int humeur, bool debut, float t, float ecoule, float dt) {
  E_recif &e = etat_ecran<E_recif>(debut);
  (void)e; (void)humeur; (void)t; (void)ecoule; (void)dt;
  degrade2(20, 20, 30, 40, 40, 60);   // A PORTER
}

// humeurs : 0 = bleu, 1 = violet
struct E_abysses { char rien; };
void s_abysses(int humeur, bool debut, float t, float ecoule, float dt) {
  E_abysses &e = etat_ecran<E_abysses>(debut);
  (void)e; (void)humeur; (void)t; (void)ecoule; (void)dt;
  degrade2(20, 20, 30, 40, 40, 60);   // A PORTER
}

// humeurs : 0 = lagune, 1 = ocean
struct E_banc { char rien; };
void s_banc(int humeur, bool debut, float t, float ecoule, float dt) {
  E_banc &e = etat_ecran<E_banc>(debut);
  (void)e; (void)humeur; (void)t; (void)ecoule; (void)dt;
  degrade2(20, 20, 30, 40, 40, 60);   // A PORTER
}

// humeurs : 0 = emeraude, 1 = dore
struct E_kelp { char rien; };
void s_kelp(int humeur, bool debut, float t, float ecoule, float dt) {
  E_kelp &e = etat_ecran<E_kelp>(debut);
  (void)e; (void)humeur; (void)t; (void)ecoule; (void)dt;
  degrade2(20, 20, 30, 40, 40, 60);   // A PORTER
}

// humeurs : 0 = bleu, 1 = plancton
struct E_baleine { char rien; };
void s_baleine(int humeur, bool debut, float t, float ecoule, float dt) {
  E_baleine &e = etat_ecran<E_baleine>(debut);
  (void)e; (void)humeur; (void)t; (void)ecoule; (void)dt;
  degrade2(20, 20, 30, 40, 40, 60);   // A PORTER
}

// humeurs : 0 = ete, 1 = coucher, 2 = orage, 3 = neon
struct E_nuages { char rien; };
void s_nuages(int humeur, bool debut, float t, float ecoule, float dt) {
  E_nuages &e = etat_ecran<E_nuages>(debut);
  (void)e; (void)humeur; (void)t; (void)ecoule; (void)dt;
  degrade2(20, 20, 30, 40, 40, 60);   // A PORTER
}

// humeurs : 0 = campagne, 1 = ville
struct E_orage { char rien; };
void s_orage(int humeur, bool debut, float t, float ecoule, float dt) {
  E_orage &e = etat_ecran<E_orage>(debut);
  (void)e; (void)humeur; (void)t; (void)ecoule; (void)dt;
  degrade2(20, 20, 30, 40, 40, 60);   // A PORTER
}

// humeurs : 0 = neon, 1 = ambre, 2 = bleu
struct E_pluie_vitre { char rien; };
void s_pluie_vitre(int humeur, bool debut, float t, float ecoule, float dt) {
  E_pluie_vitre &e = etat_ecran<E_pluie_vitre>(debut);
  (void)e; (void)humeur; (void)t; (void)ecoule; (void)dt;
  degrade2(20, 20, 30, 40, 40, 60);   // A PORTER
}

// humeurs : 0 = piscine, 1 = lagon, 2 = lune
struct E_surface { char rien; };
void s_surface(int humeur, bool debut, float t, float ecoule, float dt) {
  E_surface &e = etat_ecran<E_surface>(debut);
  (void)e; (void)humeur; (void)t; (void)ecoule; (void)dt;
  degrade2(20, 20, 30, 40, 40, 60);   // A PORTER
}

// humeurs : 0 = jour, 1 = nuit
struct E_etang { char rien; };
void s_etang(int humeur, bool debut, float t, float ecoule, float dt) {
  E_etang &e = etat_ecran<E_etang>(debut);
  (void)e; (void)humeur; (void)t; (void)ecoule; (void)dt;
  degrade2(20, 20, 30, 40, 40, 60);   // A PORTER
}

// humeurs : 0 = jour
struct E_plage { char rien; };
void s_plage(int humeur, bool debut, float t, float ecoule, float dt) {
  E_plage &e = etat_ecran<E_plage>(debut);
  (void)e; (void)humeur; (void)t; (void)ecoule; (void)dt;
  degrade2(20, 20, 30, 40, 40, 60);   // A PORTER
}

// humeurs : 0 = jungle, 1 = lune
struct E_cascade { char rien; };
void s_cascade(int humeur, bool debut, float t, float ecoule, float dt) {
  E_cascade &e = etat_ecran<E_cascade>(debut);
  (void)e; (void)humeur; (void)t; (void)ecoule; (void)dt;
  degrade2(20, 20, 30, 40, 40, 60);   // A PORTER
}
