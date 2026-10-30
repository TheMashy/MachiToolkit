// lot_espace.h -- les ecrans de ce lot, portes de machi_tool.py (croquis v10).
#pragma once

// humeurs : 0 = saturne, 1 = glace
struct E_planete { char rien; };
void s_planete(int humeur, bool debut, float t, float ecoule, float dt) {
  E_planete &e = etat_ecran<E_planete>(debut);
  (void)e; (void)humeur; (void)t; (void)ecoule; (void)dt;
  degrade2(20, 20, 30, 40, 40, 60);   // A PORTER
}

// humeurs : 0 = or, 1 = bleu
struct E_trou_noir { char rien; };
void s_trou_noir(int humeur, bool debut, float t, float ecoule, float dt) {
  E_trou_noir &e = etat_ecran<E_trou_noir>(debut);
  (void)e; (void)humeur; (void)t; (void)ecoule; (void)dt;
  degrade2(20, 20, 30, 40, 40, 60);   // A PORTER
}

// humeurs : 0 = bleu, 1 = or
struct E_galaxie { char rien; };
void s_galaxie(int humeur, bool debut, float t, float ecoule, float dt) {
  E_galaxie &e = etat_ecran<E_galaxie>(debut);
  (void)e; (void)humeur; (void)t; (void)ecoule; (void)dt;
  degrade2(20, 20, 30, 40, 40, 60);   // A PORTER
}

struct E_gravite { char rien; };
void s_gravite(int humeur, bool debut, float t, float ecoule, float dt) {
  E_gravite &e = etat_ecran<E_gravite>(debut);
  (void)e; (void)humeur; (void)t; (void)ecoule; (void)dt;
  degrade2(20, 20, 30, 40, 40, 60);   // A PORTER
}

struct E_collision { char rien; };
void s_collision(int humeur, bool debut, float t, float ecoule, float dt) {
  E_collision &e = etat_ecran<E_collision>(debut);
  (void)e; (void)humeur; (void)t; (void)ecoule; (void)dt;
  degrade2(20, 20, 30, 40, 40, 60);   // A PORTER
}

struct E_voie_lactee { char rien; };
void s_voie_lactee(int humeur, bool debut, float t, float ecoule, float dt) {
  E_voie_lactee &e = etat_ecran<E_voie_lactee>(debut);
  (void)e; (void)humeur; (void)t; (void)ecoule; (void)dt;
  degrade2(20, 20, 30, 40, 40, 60);   // A PORTER
}

struct E_eclipse { char rien; };
void s_eclipse(int humeur, bool debut, float t, float ecoule, float dt) {
  E_eclipse &e = etat_ecran<E_eclipse>(debut);
  (void)e; (void)humeur; (void)t; (void)ecoule; (void)dt;
  degrade2(20, 20, 30, 40, 40, 60);   // A PORTER
}

struct E_soleil { char rien; };
void s_soleil(int humeur, bool debut, float t, float ecoule, float dt) {
  E_soleil &e = etat_ecran<E_soleil>(debut);
  (void)e; (void)humeur; (void)t; (void)ecoule; (void)dt;
  degrade2(20, 20, 30, 40, 40, 60);   // A PORTER
}

struct E_comete { char rien; };
void s_comete(int humeur, bool debut, float t, float ecoule, float dt) {
  E_comete &e = etat_ecran<E_comete>(debut);
  (void)e; (void)humeur; (void)t; (void)ecoule; (void)dt;
  degrade2(20, 20, 30, 40, 40, 60);   // A PORTER
}

struct E_orbite { char rien; };
void s_orbite(int humeur, bool debut, float t, float ecoule, float dt) {
  E_orbite &e = etat_ecran<E_orbite>(debut);
  (void)e; (void)humeur; (void)t; (void)ecoule; (void)dt;
  degrade2(20, 20, 30, 40, 40, 60);   // A PORTER
}

struct E_constellations { char rien; };
void s_constellations(int humeur, bool debut, float t, float ecoule, float dt) {
  E_constellations &e = etat_ecran<E_constellations>(debut);
  (void)e; (void)humeur; (void)t; (void)ecoule; (void)dt;
  degrade2(20, 20, 30, 40, 40, 60);   // A PORTER
}
