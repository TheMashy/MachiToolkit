/*
 * style-frappe.js  —  a deposer dans BrainDebugger
 *
 * Mesure la maniere d'ecrire, sur les champs de TON site uniquement. Aucun
 * hook systeme, aucune capture hors de la page : ce sont les evenements
 * clavier du navigateur, sur tes propres zones de saisie. Rien de ce que tu
 * tapes ailleurs — Discord, mots de passe — n'est visible ici, par
 * construction : le navigateur ne livre ces evenements qu'a la page qui a
 * le focus, et c'est la tienne.
 *
 * Ce qui est mesure, par message :
 *   - le rythme : vitesse de frappe, longueur des rafales, pauses ;
 *   - l'hesitation : taux de correction (retours arriere), temps avant la
 *     premiere touche, temps total de redaction ;
 *   - la forme : longueur finale, nombre de revisions.
 *
 * Le CONTENU, lui, tu l'as deja cote serveur quand le message est soumis :
 * ce module n'a pas a le renvoyer, il ajoute seulement les metriques. C'est
 * la variation de ces metriques d'un jour a l'autre qui trahit un etat, pas
 * les mots eux-memes.
 *
 * Usage minimal :
 *   const style = suivreStyleFrappe(document.querySelector('#zone-chat'));
 *   // ... a l'envoi du message :
 *   envoyer({ texte, style: style.releve() });   // puis style.reset()
 */

function suivreStyleFrappe(element, options = {}) {
  const SEUIL_RAFALE = options.seuilRafale ?? 2000;   // ms de silence qui close une rafale
  const SEUIL_PAUSE  = options.seuilPause  ?? 1000;    // ms au-dela = pause notable

  let etat = neuf();

  function neuf() {
    return {
      touches: 0,
      corrections: 0,        // Backspace + Delete
      debut: 0,              // horodatage de la premiere touche
      derniere: 0,           // horodatage de la derniere touche
      actif: 0,              // ms passees a frapper (hors longues pauses)
      rafales: [],           // longueur de chaque rafale close
      rafale: 0,             // rafale en cours
      pauses: 0,
      pauseMax: 0,
      revisions: 0,          // combien de fois on repart apres une pause
    };
  }

  function onKeydown(ev) {
    const t = ev.timeStamp || performance.now();
    const correction = ev.key === 'Backspace' || ev.key === 'Delete';

    // On ne compte que ce qui produit ou efface du texte : les fleches, Ctrl,
    // Alt, Tab... ne sont pas de la frappe.
    const frappe = correction || ev.key.length === 1;
    if (!frappe) return;

    if (!etat.debut) etat.debut = t;
    const ecart = etat.derniere ? t - etat.derniere : 0;
    etat.derniere = t;

    etat.touches++;
    if (correction) etat.corrections++;

    if (ecart > 0 && ecart <= SEUIL_RAFALE) {
      etat.actif += ecart;
      etat.rafale++;
    } else {
      if (etat.rafale > 0) etat.rafales.push(etat.rafale);
      etat.rafale = 1;
      if (ecart > SEUIL_PAUSE) {
        etat.pauses++;
        etat.revisions++;
        etat.pauseMax = Math.max(etat.pauseMax, Math.min(ecart, 600000));
      }
    }
  }

  element.addEventListener('keydown', onKeydown, true);

  return {
    /* Renvoie le digest du message en cours. A appeler a l'envoi. */
    releve() {
      const rafales = etat.rafales.concat(etat.rafale ? [etat.rafale] : []);
      const minutes = etat.actif / 60000;
      const longueur = (element.value ?? element.textContent ?? '').length;
      return {
        touches: etat.touches,
        longueur_finale: longueur,
        corrections_pct: etat.touches
          ? Math.round((1000 * etat.corrections) / etat.touches) / 10 : 0,
        vitesse_touches_min: minutes > 0.01     // > ~0,6 s de frappe active
          ? Math.round(etat.touches / minutes) : 0,
        rafale_moyenne: rafales.length
          ? Math.round((10 * rafales.reduce((a, b) => a + b, 0)) / rafales.length) / 10 : 0,
        pauses: etat.pauses,
        pause_max_s: Math.round(etat.pauseMax / 100) / 10,
        revisions: etat.revisions,
        redaction_s: etat.debut ? Math.round((etat.derniere - etat.debut) / 100) / 10 : 0,
      };
    },

    /* A appeler apres l'envoi, pour repartir a zero sur le prochain message. */
    reset() { etat = neuf(); },

    /* Pour tout arreter proprement. */
    detacher() { element.removeEventListener('keydown', onKeydown, true); },
  };
}

// Exemple d'agregation d'une journee, cote site, pour donner du contexte au
// chatbot sans lui envoyer une seule phrase :
//
//   const jour = releves.reduce((acc, r) => {
//     acc.messages++;
//     acc.vitesse += r.vitesse_touches_min;
//     acc.corrections += r.corrections_pct;
//     acc.revisions += r.revisions;
//     return acc;
//   }, { messages: 0, vitesse: 0, corrections: 0, revisions: 0 });
//   const moyenne = {
//     vitesse: jour.vitesse / jour.messages,
//     corrections: jour.corrections / jour.messages,
//     revisions: jour.revisions / jour.messages,
//   };
//   // "Aujourd'hui : frappe plus lente que d'habitude, plus de corrections,
//   //  messages plus courts" — c'est ce genre de resume que le bot lit.

if (typeof module !== 'undefined') module.exports = { suivreStyleFrappe };
