# Compagnons BrainDebugger

Deux briques front, a deposer dans le site
[BrainDebugger](https://braindebugger-production.up.railway.app), pas dans
Machi Tool. Elles vivent ici pour etre versionnees avec l'application qui
produit la donnee qu'elles consomment.

## quantified-self.html

Onglet « Quantified Self » : aperçu des JSON d'activite ecrits par Machi
Tool, et export d'un **rollup consolide** — un seul objet, a jour, que le
site stocke une fois au lieu de reparser chaque journee.

Trois sources : synchro live (`GET 127.0.0.1:7373/activite` avec le jeton
de la passerelle locale), depot d'un `activite.jsonl`, ou donnees d'exemple.
Autonome : aucun script externe. Le bouton de telechargement suppose une
page servie par le site (le bac a sable d'un apercu bloque les
telechargements).

## style-frappe.js

Mesure la maniere d'ecrire sur les champs du site — vitesse, rafales,
pauses, corrections, revisions par message. Cote navigateur, sur les seuls
champs de BrainDebugger : rien de ce qui est tape ailleurs n'est visible.
C'est la ou se mesure le rythme d'ecriture, la ou l'application, elle, ne
capte aucun contenu.

    const style = suivreStyleFrappe(document.querySelector('#zone-chat'));
    // a l'envoi : envoyer({ texte, style: style.releve() }); style.reset();
