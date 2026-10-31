// lot_instants_c.h -- les ecrans de ce lot, portes de machi_tool.py (croquis v10).
#pragma once

struct E_quai_gare { char rien; };
void s_quai_gare(int humeur, bool debut, float t, float ecoule, float dt) {
  E_quai_gare &e = etat_ecran<E_quai_gare>(debut);
  (void)e; (void)humeur; (void)t; (void)ecoule; (void)dt;
  degrade2(20, 20, 30, 40, 40, 60);   // A PORTER
}

struct E_metro { char rien; };
void s_metro(int humeur, bool debut, float t, float ecoule, float dt) {
  E_metro &e = etat_ecran<E_metro>(debut);
  (void)e; (void)humeur; (void)t; (void)ecoule; (void)dt;
  degrade2(20, 20, 30, 40, 40, 60);   // A PORTER
}

struct E_toit { char rien; };
void s_toit(int humeur, bool debut, float t, float ecoule, float dt) {
  E_toit &e = etat_ecran<E_toit>(debut);
  (void)e; (void)humeur; (void)t; (void)ecoule; (void)dt;
  degrade2(20, 20, 30, 40, 40, 60);   // A PORTER
}

struct E_carrefour { char rien; };
void s_carrefour(int humeur, bool debut, float t, float ecoule, float dt) {
  E_carrefour &e = etat_ecran<E_carrefour>(debut);
  (void)e; (void)humeur; (void)t; (void)ecoule; (void)dt;
  degrade2(20, 20, 30, 40, 40, 60);   // A PORTER
}
