// lot_villes3d.h -- les ecrans de ce lot, portes de machi_tool.py (croquis v10).
#pragma once

struct E_cyber_3d { char rien; };
void s_cyber_3d(int humeur, bool debut, float t, float ecoule, float dt) {
  E_cyber_3d &e = etat_ecran<E_cyber_3d>(debut);
  (void)e; (void)humeur; (void)t; (void)ecoule; (void)dt;
  degrade2(20, 20, 30, 40, 40, 60);   // A PORTER
}

struct E_survol { char rien; };
void s_survol(int humeur, bool debut, float t, float ecoule, float dt) {
  E_survol &e = etat_ecran<E_survol>(debut);
  (void)e; (void)humeur; (void)t; (void)ecoule; (void)dt;
  degrade2(20, 20, 30, 40, 40, 60);   // A PORTER
}

struct E_ruelle { char rien; };
void s_ruelle(int humeur, bool debut, float t, float ecoule, float dt) {
  E_ruelle &e = etat_ecran<E_ruelle>(debut);
  (void)e; (void)humeur; (void)t; (void)ecoule; (void)dt;
  degrade2(20, 20, 30, 40, 40, 60);   // A PORTER
}

struct E_pare_brise { char rien; };
void s_pare_brise(int humeur, bool debut, float t, float ecoule, float dt) {
  E_pare_brise &e = etat_ecran<E_pare_brise>(debut);
  (void)e; (void)humeur; (void)t; (void)ecoule; (void)dt;
  degrade2(20, 20, 30, 40, 40, 60);   // A PORTER
}

struct E_pont { char rien; };
void s_pont(int humeur, bool debut, float t, float ecoule, float dt) {
  E_pont &e = etat_ecran<E_pont>(debut);
  (void)e; (void)humeur; (void)t; (void)ecoule; (void)dt;
  degrade2(20, 20, 30, 40, 40, 60);   // A PORTER
}

struct E_grande_roue { char rien; };
void s_grande_roue(int humeur, bool debut, float t, float ecoule, float dt) {
  E_grande_roue &e = etat_ecran<E_grande_roue>(debut);
  (void)e; (void)humeur; (void)t; (void)ecoule; (void)dt;
  degrade2(20, 20, 30, 40, 40, 60);   // A PORTER
}

struct E_voxel { char rien; };
void s_voxel(int humeur, bool debut, float t, float ecoule, float dt) {
  E_voxel &e = etat_ecran<E_voxel>(debut);
  (void)e; (void)humeur; (void)t; (void)ecoule; (void)dt;
  degrade2(20, 20, 30, 40, 40, 60);   // A PORTER
}

struct E_ocean { char rien; };
void s_ocean(int humeur, bool debut, float t, float ecoule, float dt) {
  E_ocean &e = etat_ecran<E_ocean>(debut);
  (void)e; (void)humeur; (void)t; (void)ecoule; (void)dt;
  degrade2(20, 20, 30, 40, 40, 60);   // A PORTER
}
