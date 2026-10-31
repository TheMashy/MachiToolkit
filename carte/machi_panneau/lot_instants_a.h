// lot_instants_a.h -- les ecrans de ce lot, portes de machi_tool.py (croquis v10).
#pragma once

struct E_arret_bus { char rien; };
void s_arret_bus(int humeur, bool debut, float t, float ecoule, float dt) {
  E_arret_bus &e = etat_ecran<E_arret_bus>(debut);
  (void)e; (void)humeur; (void)t; (void)ecoule; (void)dt;
  degrade2(20, 20, 30, 40, 40, 60);   // A PORTER
}

struct E_superette { char rien; };
void s_superette(int humeur, bool debut, float t, float ecoule, float dt) {
  E_superette &e = etat_ecran<E_superette>(debut);
  (void)e; (void)humeur; (void)t; (void)ecoule; (void)dt;
  degrade2(20, 20, 30, 40, 40, 60);   // A PORTER
}

struct E_distributeur { char rien; };
void s_distributeur(int humeur, bool debut, float t, float ecoule, float dt) {
  E_distributeur &e = etat_ecran<E_distributeur>(debut);
  (void)e; (void)humeur; (void)t; (void)ecoule; (void)dt;
  degrade2(20, 20, 30, 40, 40, 60);   // A PORTER
}

struct E_cabine { char rien; };
void s_cabine(int humeur, bool debut, float t, float ecoule, float dt) {
  E_cabine &e = etat_ecran<E_cabine>(debut);
  (void)e; (void)humeur; (void)t; (void)ecoule; (void)dt;
  degrade2(20, 20, 30, 40, 40, 60);   // A PORTER
}
