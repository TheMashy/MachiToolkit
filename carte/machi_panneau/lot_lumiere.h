// lot_lumiere.h -- les ecrans de ce lot, portes de machi_tool.py (croquis v10).
#pragma once

struct E_j_etoiles { char rien; };
void j_etoiles(int humeur, bool debut, float t, float ecoule, float dt) {
  E_j_etoiles &e = etat_ecran<E_j_etoiles>(debut);
  (void)e; (void)humeur; (void)t; (void)ecoule; (void)dt;
  degrade2(20, 20, 30, 40, 40, 60);   // A PORTER
}

struct E_j_matrice { char rien; };
void j_matrice(int humeur, bool debut, float t, float ecoule, float dt) {
  E_j_matrice &e = etat_ecran<E_j_matrice>(debut);
  (void)e; (void)humeur; (void)t; (void)ecoule; (void)dt;
  degrade2(20, 20, 30, 40, 40, 60);   // A PORTER
}

struct E_j_plasma { char rien; };
void j_plasma(int humeur, bool debut, float t, float ecoule, float dt) {
  E_j_plasma &e = etat_ecran<E_j_plasma>(debut);
  (void)e; (void)humeur; (void)t; (void)ecoule; (void)dt;
  degrade2(20, 20, 30, 40, 40, 60);   // A PORTER
}

struct E_j_feu { char rien; };
void j_feu(int humeur, bool debut, float t, float ecoule, float dt) {
  E_j_feu &e = etat_ecran<E_j_feu>(debut);
  (void)e; (void)humeur; (void)t; (void)ecoule; (void)dt;
  degrade2(20, 20, 30, 40, 40, 60);   // A PORTER
}

struct E_j_vie { char rien; };
void j_vie(int humeur, bool debut, float t, float ecoule, float dt) {
  E_j_vie &e = etat_ecran<E_j_vie>(debut);
  (void)e; (void)humeur; (void)t; (void)ecoule; (void)dt;
  degrade2(20, 20, 30, 40, 40, 60);   // A PORTER
}

struct E_j_tunnel { char rien; };
void j_tunnel(int humeur, bool debut, float t, float ecoule, float dt) {
  E_j_tunnel &e = etat_ecran<E_j_tunnel>(debut);
  (void)e; (void)humeur; (void)t; (void)ecoule; (void)dt;
  degrade2(20, 20, 30, 40, 40, 60);   // A PORTER
}

struct E_j_lave { char rien; };
void j_lave(int humeur, bool debut, float t, float ecoule, float dt) {
  E_j_lave &e = etat_ecran<E_j_lave>(debut);
  (void)e; (void)humeur; (void)t; (void)ecoule; (void)dt;
  degrade2(20, 20, 30, 40, 40, 60);   // A PORTER
}

struct E_j_artifice { char rien; };
void j_artifice(int humeur, bool debut, float t, float ecoule, float dt) {
  E_j_artifice &e = etat_ecran<E_j_artifice>(debut);
  (void)e; (void)humeur; (void)t; (void)ecoule; (void)dt;
  degrade2(20, 20, 30, 40, 40, 60);   // A PORTER
}

struct E_j_tuyaux { char rien; };
void j_tuyaux(int humeur, bool debut, float t, float ecoule, float dt) {
  E_j_tuyaux &e = etat_ecran<E_j_tuyaux>(debut);
  (void)e; (void)humeur; (void)t; (void)ecoule; (void)dt;
  degrade2(20, 20, 30, 40, 40, 60);   // A PORTER
}

struct E_j_rebond { char rien; };
void j_rebond(int humeur, bool debut, float t, float ecoule, float dt) {
  E_j_rebond &e = etat_ecran<E_j_rebond>(debut);
  (void)e; (void)humeur; (void)t; (void)ecoule; (void)dt;
  degrade2(20, 20, 30, 40, 40, 60);   // A PORTER
}

struct E_j_ondes { char rien; };
void j_ondes(int humeur, bool debut, float t, float ecoule, float dt) {
  E_j_ondes &e = etat_ecran<E_j_ondes>(debut);
  (void)e; (void)humeur; (void)t; (void)ecoule; (void)dt;
  degrade2(20, 20, 30, 40, 40, 60);   // A PORTER
}
