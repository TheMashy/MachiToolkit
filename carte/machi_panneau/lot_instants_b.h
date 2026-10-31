// lot_instants_b.h -- les ecrans de ce lot, portes de machi_tool.py (croquis v10).
#pragma once

struct E_ramen { char rien; };
void s_ramen(int humeur, bool debut, float t, float ecoule, float dt) {
  E_ramen &e = etat_ecran<E_ramen>(debut);
  (void)e; (void)humeur; (void)t; (void)ecoule; (void)dt;
  degrade2(20, 20, 30, 40, 40, 60);   // A PORTER
}

struct E_laverie { char rien; };
void s_laverie(int humeur, bool debut, float t, float ecoule, float dt) {
  E_laverie &e = etat_ecran<E_laverie>(debut);
  (void)e; (void)humeur; (void)t; (void)ecoule; (void)dt;
  degrade2(20, 20, 30, 40, 40, 60);   // A PORTER
}

struct E_diner { char rien; };
void s_diner(int humeur, bool debut, float t, float ecoule, float dt) {
  E_diner &e = etat_ecran<E_diner>(debut);
  (void)e; (void)humeur; (void)t; (void)ecoule; (void)dt;
  degrade2(20, 20, 30, 40, 40, 60);   // A PORTER
}

struct E_station_service { char rien; };
void s_station_service(int humeur, bool debut, float t, float ecoule, float dt) {
  E_station_service &e = etat_ecran<E_station_service>(debut);
  (void)e; (void)humeur; (void)t; (void)ecoule; (void)dt;
  degrade2(20, 20, 30, 40, 40, 60);   // A PORTER
}
