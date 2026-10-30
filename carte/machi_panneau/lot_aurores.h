// lot_aurores.h -- les ecrans de ce lot, portes de machi_tool.py (croquis v10).
#pragma once

struct E_boreal { char rien; };
void s_boreal(int humeur, bool debut, float t, float ecoule, float dt) {
  E_boreal &e = etat_ecran<E_boreal>(debut);
  (void)e; (void)humeur; (void)t; (void)ecoule; (void)dt;
  degrade2(20, 20, 30, 40, 40, 60);   // A PORTER
}

struct E_tunnel_boreal { char rien; };
void s_tunnel_boreal(int humeur, bool debut, float t, float ecoule, float dt) {
  E_tunnel_boreal &e = etat_ecran<E_tunnel_boreal>(debut);
  (void)e; (void)humeur; (void)t; (void)ecoule; (void)dt;
  degrade2(20, 20, 30, 40, 40, 60);   // A PORTER
}
