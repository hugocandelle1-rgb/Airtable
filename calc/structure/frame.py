"""Bâti en profilés aluminium : fréquences propres (EF poutres 3D), raideur
locale sous les appuis, caisson de plenum suspendu (panneaux sous 400 Pa,
masse), manchon souple et membrane roulante.

Deux bâtis :
  - « reference » : bâti autonome sur 4 pieds réglables, profilés Bosch Rexroth
    rainure 10 (cadre supérieur 45×90 posé « de chant », montants 45×90,
    ceinture basse et étagère 45×45), contreventé par écharpes 45×45 ;
  - « paillasse » (variante économique) : cadre bas 45×45 posé sur une table de
    laboratoire existante (montants de 300 mm).

La plaque et son caisson (corps rigide, masse lue dans support_study.json)
reposent sur le cadre supérieur par 3 appuis cinématiques (ressorts 3D).
Les assemblages de profilés sont semi-rigides : modélisés par des tronçons
d'extrémité de 20 mm à inertie réduite (facteur `joint_factor`), avec un cas
« assemblages rigides » en borne haute.

Propriétés de section : docs/research/profiles_alu_et_mecanique.md (Rexroth
45×45 : I = 11,7 cm⁴, retenue la valeur basse ; 45×90 : 82 / 23,6 cm⁴).
Constante de torsion : non publiée dans la veille ⇒ hypothèse J = 0,3·(Iy+Iz).

    python3 -m calc.structure.frame
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import numpy as np
import scipy.linalg as sla

from calc.common.params import REPO_ROOT, load_params

RES = REPO_ROOT / "calc" / "structure" / "results"
FIG = REPO_ROOT / "calc" / "structure" / "figures"

E_AL, G_AL, RHO_AL = 70e9, 26e9, 2700.0
PROFILES = {
    # A (m²), Iy (axe faible ou égal), Iz (axe fort), masse linéique (kg/m) ; axe fort = flexion dans le plan local (x, z_local)
    "45x45": dict(A=6.0e-4, I1=11.7e-8, I2=11.7e-8, m=1.6),
    "45x90": dict(A=11.3e-4, I1=23.6e-8, I2=82.0e-8, m=3.0),
}


# -----------------------------------------------------------------------------
# Élément poutre 3D (Euler-Bernoulli), matrices de rigidité et de masse cohérente
# -----------------------------------------------------------------------------

def beam_matrices(L, A, Iy, Iz, J, m_lin, E=E_AL, G=G_AL):
    """Repère local : x le long de la poutre ; Iz pour la flexion dans le plan
    (x, y), Iy pour la flexion dans le plan (x, z)."""
    K = np.zeros((12, 12))
    EA, GJ = E * A / L, G * J / L
    K[0, 0] = K[6, 6] = EA; K[0, 6] = K[6, 0] = -EA
    K[3, 3] = K[9, 9] = GJ; K[3, 9] = K[9, 3] = -GJ
    for (I, v, t, s) in ((Iz, 1, 5, 1), (Iy, 2, 4, -1)):
        c = E * I / L**3
        idx = [v, t, v + 6, t + 6]
        k = c * np.array([[12, 6 * L, -12, 6 * L], [6 * L, 4 * L**2, -6 * L, 2 * L**2],
                          [-12, -6 * L, 12, -6 * L], [6 * L, 2 * L**2, -6 * L, 4 * L**2]])
        sg = np.array([1, s, 1, s])
        k = k * np.outer(sg, sg)
        for a in range(4):
            for b in range(4):
                K[idx[a], idx[b]] += k[a, b]
    M = np.zeros((12, 12))
    mL = m_lin * L
    M[0, 0] = M[6, 6] = mL / 3; M[0, 6] = M[6, 0] = mL / 6
    rx = (Iy + Iz) / A * mL
    M[3, 3] = M[9, 9] = rx / 3; M[3, 9] = M[9, 3] = rx / 6
    for (v, t, s) in ((1, 5, 1), (2, 4, -1)):
        idx = [v, t, v + 6, t + 6]
        m = mL / 420 * np.array([[156, 22 * L, 54, -13 * L], [22 * L, 4 * L**2, 13 * L, -3 * L**2],
                                 [54, 13 * L, 156, -22 * L], [-13 * L, -3 * L**2, -22 * L, 4 * L**2]])
        sg = np.array([1, s, 1, s])
        m = m * np.outer(sg, sg)
        for a in range(4):
            for b in range(4):
                M[idx[a], idx[b]] += m[a, b]
    return K, M


def rotation(p1, p2, strong_dir):
    """Matrice 3×3 (lignes = axes locaux) ; strong_dir = direction (globale) de la
    grande dimension de la section (flexion autour de l'axe fort)."""
    ex = (p2 - p1) / np.linalg.norm(p2 - p1)
    ref = np.asarray(strong_dir, float)
    if abs(np.dot(ref, ex)) > 0.99:
        ref = np.array([1.0, 0, 0]) if abs(ex[0]) < 0.9 else np.array([0, 1.0, 0])
    ey = ref - np.dot(ref, ex) * ex
    ey /= np.linalg.norm(ey)
    ez = np.cross(ex, ey)
    return np.vstack([ex, ey, ez])


class Frame:
    def __init__(self):
        self.nodes = []
        self.elems = []
        self.point_masses = {}
        self.springs = []         # (node_frame, body_point_offset, k_vec)
        self.body = None          # (mass, inertia 3×3, cg)

    def node(self, xyz):
        xyz = np.asarray(xyz, float)
        for i, p in enumerate(self.nodes):
            if np.linalg.norm(p - xyz) < 1e-6:
                return i
        self.nodes.append(xyz)
        return len(self.nodes) - 1

    def member(self, p1, p2, prof, strong_dir, nseg=4, joint_factor=1.0, joint_len=0.02, breaks=()):
        """Membrure subdivisée ; tronçons d'extrémité à inertie réduite (assemblage).
        `breaks` : abscisses (m) où un nœud est imposé (membrure continue)."""
        p1, p2 = np.asarray(p1, float), np.asarray(p2, float)
        L = np.linalg.norm(p2 - p1)
        u = (p2 - p1) / L
        cuts = [0.0] + [b for b in breaks if 0 < b < L]
        if joint_factor < 1.0:
            cuts.append(joint_len)
        cuts += list(np.linspace(joint_len if joint_factor < 1 else 0, L - (joint_len if joint_factor < 1 else 0),
                                 nseg + 1)[1:-1])
        if joint_factor < 1.0:
            cuts.append(L - joint_len)
        cuts.append(L)
        cuts = sorted(set(np.round(cuts, 9)))
        pr = PROFILES[prof]
        for a, b in zip(cuts[:-1], cuts[1:]):
            na, nb = self.node(p1 + a * u), self.node(p1 + b * u)
            is_joint = joint_factor < 1.0 and (a < 1e-9 or b > L - 1e-9)
            f = joint_factor if is_joint else 1.0
            self.elems.append(dict(n=(na, nb), A=pr["A"], I1=pr["I1"] * f, I2=pr["I2"] * f,
                                   J=0.3 * (pr["I1"] + pr["I2"]) * f, m=pr["m"], strong=strong_dir))

    def assemble(self, fixed_nodes):
        nn = len(self.nodes)
        nd = 6 * nn + (6 if self.body else 0)
        K = np.zeros((nd, nd)); M = np.zeros((nd, nd))
        for e in self.elems:
            na, nb = e["n"]
            p1, p2 = self.nodes[na], self.nodes[nb]
            L = np.linalg.norm(p2 - p1)
            R = rotation(p1, p2, e["strong"])
            # axe fort : flexion dans le plan (x, y_local) où y_local = strong_dir → Iz = I2
            Ke, Me = beam_matrices(L, e["A"], e["I1"], e["I2"], e["J"], e["m"])
            T = np.kron(np.eye(4), R)
            Kg, Mg = T.T @ Ke @ T, T.T @ Me @ T
            idx = np.r_[6 * na:6 * na + 6, 6 * nb:6 * nb + 6]
            K[np.ix_(idx, idx)] += Kg
            M[np.ix_(idx, idx)] += Mg
        for n, m in self.point_masses.items():
            for k in range(3):
                M[6 * n + k, 6 * n + k] += m
        if self.body:
            mb, Ib, cg = self.body
            ib = 6 * nn
            M[ib:ib + 3, ib:ib + 3] += mb * np.eye(3)
            M[ib + 3:ib + 6, ib + 3:ib + 6] += Ib
            for n, pt, kv in self.springs:
                r = np.asarray(pt) - cg
                # déplacement du point du corps : u + θ × r = u − [r]× θ
                Rx = np.array([[0, -r[2], r[1]], [r[2], 0, -r[0]], [-r[1], r[0], 0]])
                Bb = np.hstack([np.eye(3), -Rx])
                Bf = np.zeros((3, nd)); Bf[:, 6 * n:6 * n + 3] = np.eye(3)
                Bfull = Bf.copy(); Bfull[:, ib:ib + 6] -= Bb
                K += Bfull.T @ np.diag(kv) @ Bfull
        free = np.ones(nd, bool)
        for n in fixed_nodes:
            free[6 * n:6 * n + 3] = False           # pieds : rotule (translations bloquées)
        return K, M, free

    def modes(self, fixed_nodes, nmodes=8):
        K, M, free = self.assemble(fixed_nodes)
        Kf, Mf = K[np.ix_(free, free)], M[np.ix_(free, free)]
        vals, vecs = sla.eigh(Kf, Mf, subset_by_index=[0, nmodes - 1])
        f = np.sqrt(np.maximum(vals, 0)) / (2 * np.pi)
        full = np.zeros((K.shape[0], nmodes)); full[free] = vecs
        return f, full

    def static(self, fixed_nodes, F):
        K, M, free = self.assemble(fixed_nodes)
        u = np.zeros(K.shape[0])
        u[free] = np.linalg.solve(K[np.ix_(free, free)], F[free])
        return u

    def mass(self):
        m = sum(e["m"] * np.linalg.norm(self.nodes[e["n"][1]] - self.nodes[e["n"][0]]) for e in self.elems)
        return m + sum(self.point_masses.values()) + (self.body[0] if self.body else 0)


def payload():
    """Masse portée (plaque + caisson + accessoires) et appuis du schéma retenu."""
    f = RES / "support_study.json"
    if f.exists():
        d = json.loads(f.read_text())
        sel = d["selected"]
        R = np.array(sel["by_thickness"]["35"]["B"]["R_G_N"])
        return R.sum() / 9.81, np.array(sel["points_mm"]) * 1e-3
    return 36.0, np.array([[0, 0.2425], [0.2425, -0.1455], [-0.2425, -0.1455]])


def build(kind="reference", bracing="3faces", joint_factor=0.25, k_sup=3.0e7):
    fr = Frame()
    a = 0.25                                   # demi-côté de l'axe du cadre supérieur
    m_pl, sup = payload()
    if kind == "reference":
        z_ring, z_low, z_shelf = 0.745, 0.15, 0.42
        top, leg, low = "45x90", "45x90", "45x45"
    else:
        z_ring, z_low, z_shelf = 0.30, None, None
        top, leg, low = "45x45", "45x45", "45x45"
    C = [(-a, -a), (a, -a), (a, a), (-a, a)]
    # cadre supérieur (grande dimension verticale)
    for i in range(4):
        (x1, y1), (x2, y2) = C[i], C[(i + 1) % 4]
        fr.member((x1, y1, z_ring), (x2, y2, z_ring), top, (0, 0, 1), nseg=6, joint_factor=joint_factor)
    feet = []
    for x, y in C:
        fr.member((x, y, 0.0), (x, y, z_ring), leg, (1, 0, 0), nseg=6, joint_factor=joint_factor,
                  breaks=[zz for zz in (z_low, z_shelf) if zz is not None])
        feet.append(fr.node((x, y, 0.0)))
    for z in [zz for zz in (z_low, z_shelf) if zz is not None]:
        for i in range(4):
            (x1, y1), (x2, y2) = C[i], C[(i + 1) % 4]
            fr.member((x1, y1, z), (x2, y2, z), low, (0, 0, 1), nseg=4, joint_factor=joint_factor)
    # écharpes de contreventement (diagonales 45×45 dans les faces verticales)
    faces = {"arriere": (C[2], C[3]), "gauche": (C[3], C[0]), "droite": (C[1], C[2]), "avant": (C[0], C[1])}
    use = {"aucun": [], "3faces": ["arriere", "gauche", "droite"], "4faces": list(faces)}[bracing]
    zb = z_low if z_low is not None else 0.0
    for fname in use:
        (x1, y1), (x2, y2) = faces[fname]
        fr.member((x1, y1, zb), (x2, y2, z_ring), low, (0, 0, 1), nseg=4, joint_factor=joint_factor)
    # masses : ventilateur + caisson filtre sur l'étagère (référence), électronique
    if z_shelf is not None:
        for x, y in C:
            fr.point_masses[fr.node((x, y, z_shelf))] = fr.point_masses.get(fr.node((x, y, z_shelf)), 0) + 1.5
    # plaque + caisson : corps rigide sur 3 appuis (points sur le cadre)
    z_plate_cg = z_ring + 0.045 + 0.045 + 0.0175 - 0.04   # haut cadre + vérin, plaque ; caisson abaisse le CG
    cg = np.array([0.0, 0.0, z_plate_cg])
    Lp = 0.52
    I = m_pl * np.diag([(Lp**2 + 0.2**2) / 12, (Lp**2 + 0.2**2) / 12, Lp**2 / 6])
    fr.body = (m_pl, I, cg)
    for (x, y) in sup:
        # nœud du cadre le plus proche du point d'appui (sur l'axe du cadre)
        xs = np.clip(x, -a, a); ys = np.clip(y, -a, a)
        if abs(abs(x) - a) < abs(abs(y) - a):
            xs = np.sign(x) * a
        else:
            ys = np.sign(y) * a
        cand = [i for i, p in enumerate(fr.nodes) if abs(p[2] - z_ring) < 1e-6]
        n = min(cand, key=lambda i: np.hypot(fr.nodes[i][0] - xs, fr.nodes[i][1] - ys))
        fr.springs.append((n, (x, y, z_ring + 0.0675), np.array([k_sup, k_sup, k_sup])))
    return fr, feet


def mode_label(fr, vec):
    nn = len(fr.nodes)
    b = vec[6 * nn:6 * nn + 6]
    u = vec[:6 * nn].reshape(nn, 6)[:, :3]
    top = np.array([p[2] for p in fr.nodes]) > 0.2
    ux, uy, uz = np.abs(u[top]).mean(axis=0)
    rot = np.abs(b[3:6])
    if np.abs(b[2]) > 0.5 * max(np.abs(b[0]), np.abs(b[1]), 1e-12) and np.abs(b[2]) > 1e-3 * np.abs(vec).max():
        return "pompage vertical"
    if rot[2] > 3 * max(rot[0], rot[1]):
        return "torsion autour de z"
    if ux > 2 * uy:
        return "balancement x"
    if uy > 2 * ux:
        return "balancement y"
    return "mixte"


# -----------------------------------------------------------------------------
# Panneaux sous pression, caisson, manchon, membrane
# -----------------------------------------------------------------------------

def navier_rect(a, b, t, p, E, nu, nterms=41):
    """Plaque rectangulaire simplement appuyée sous pression : w_max, σ_max."""
    D = E * t**3 / (12 * (1 - nu**2))
    w = Mx = My = 0.0
    for m in range(1, nterms + 1, 2):
        for n in range(1, nterms + 1, 2):
            c = 16 * p / (np.pi**6 * D * m * n * ((m / a) ** 2 + (n / b) ** 2) ** 2)
            s = np.sin(m * np.pi / 2) * np.sin(n * np.pi / 2)
            w += c * s
            Mx += D * c * s * ((m * np.pi / a) ** 2 + nu * (n * np.pi / b) ** 2)
            My += D * c * s * ((n * np.pi / b) ** 2 + nu * (m * np.pi / a) ** 2)
    return w, 6 * max(Mx, My) / t**2


def panels(P):
    p = P["operating"]["p_plenum_max_Pa"]
    rows = []
    for name, a, b, t, E, nu, rho in (
            ("fond caisson alu 6 mm", 0.430, 0.430, 0.006, 70e9, 0.33, 2700),
            ("paroi caisson alu 6 mm", 0.430, 0.160, 0.006, 70e9, 0.33, 2700),
            ("paroi caisson alu 4 mm", 0.430, 0.160, 0.004, 70e9, 0.33, 2700),
            ("hublot PC 6 mm (paroi)", 0.430, 0.160, 0.006, 2.3e9, 0.37, 1200),
            ("fond PMMA 8 mm", 0.430, 0.430, 0.008, 3.2e9, 0.37, 1190),
            ("panneau bâti alu composite 4 mm (non pressurisé, info)", 0.45, 0.45, 0.004, 20e9, 0.3, 1400)):
        w, s = navier_rect(a, b, t, p, E, nu)
        rows.append(dict(panel=name, a_mm=a * 1e3, b_mm=b * 1e3, t_mm=t * 1e3, w_max_um=w * 1e6, sigma_MPa=s / 1e6,
                         mass_kg=a * b * t * rho))
    # masse du caisson suspendu (parois 6 mm, fond 6 mm, tôle inox 1 mm, divers)
    walls = 4 * 0.436 * 0.165 * 0.006 * 2700
    bottom = 0.442**2 * 0.006 * 2700
    baffle = 0.43**2 * 0.001 * 7900 * (1 - 0.057)
    misc = 0.5 + 0.17 + 0.2
    box = dict(walls_kg=walls, bottom_kg=bottom, baffle_kg=baffle, misc_kg=misc, total_kg=walls + bottom + baffle + misc)
    # manchon souple Ø80 : poussée p·A transmise au caisson (chemin B)
    sleeve = dict(d_mm=80, thrust_N=p * np.pi * 0.08**2 / 4)
    # membrane roulante semi-circulaire (variante chemin A) : rayon de boucle 8 mm
    r = 0.008
    T = p * r
    memb = dict(loop_radius_mm=r * 1e3, tension_N_m=T, stress_kPa_t0p4=T / 0.0004 / 1e3,
                note="Boucle entre chant de plaque et paroi verticale : l'aire efficace ne dépend pas du "
                     "déplacement vertical (roulement), seulement du jeu horizontal (±0,5 mm → ±0,6 % de la "
                     "force de pression sur 440 mm).")
    return dict(p_Pa=p, panels=rows, box=box, sleeve=sleeve, membrane_A=memb)


def run(P=None, verbose=True):
    P = P or load_params()
    out = dict(cases=[])
    for kind, bracing, jf in (("reference", "aucun", 0.25), ("reference", "3faces", 0.25),
                              ("reference", "4faces", 0.25), ("reference", "3faces", 1.0),
                              ("paillasse", "aucun", 0.25), ("paillasse", "3faces", 0.25)):
        fr, feet = build(kind, bracing, jf)
        f, V = fr.modes(feet, nmodes=8)
        labels = [mode_label(fr, V[:, i]) for i in range(len(f))]
        rec = dict(kind=kind, bracing=bracing, joint_factor=jf, f_Hz=f.tolist(), labels=labels,
                   frame_mass_kg=fr.mass() - fr.body[0], n_dof=6 * len(fr.nodes) + 6)
        out["cases"].append(rec)
        if verbose:
            print(f"{kind:9s} contrev. {bracing:6s} assemblages ×{jf:.2f} : " +
                  ", ".join(f"{fi:.0f} Hz ({lb})" for fi, lb in zip(f[:5], labels[:5])) +
                  f" ; masse profilés {rec['frame_mass_kg']:.1f} kg")
    # raideur verticale locale du cadre sous un appui (référence, 3 faces)
    fr, feet = build("reference", "3faces", 0.25)
    fr.body = None; fr.springs = []
    kloc = []
    m_pl, sup = payload()
    for (x, y) in sup:
        a = 0.25
        cand = [i for i, p in enumerate(fr.nodes) if abs(p[2] - 0.745) < 1e-6]
        xs, ys = (np.sign(x) * a, y) if abs(abs(x) - a) < abs(abs(y) - a) else (x, np.sign(y) * a)
        n = min(cand, key=lambda i: np.hypot(fr.nodes[i][0] - xs, fr.nodes[i][1] - ys))
        F = np.zeros(6 * len(fr.nodes)); F[6 * n + 2] = -1.0
        u = fr.static(feet, F)
        kloc.append(1 / abs(u[6 * n + 2]))
    out["k_local_support_N_m"] = kloc
    out["panels"] = panels(P)
    if verbose:
        print(f"Raideur verticale du cadre sous les appuis : {np.round(np.array(kloc)/1e6, 1).tolist()} N/µm")
        pp = out["panels"]
        for r in pp["panels"]:
            print(f"  {r['panel']:45s} {r['a_mm']:.0f}×{r['b_mm']:.0f}×{r['t_mm']:.0f} : w_max {r['w_max_um']:.0f} µm, "
                  f"σ {r['sigma_MPa']:.2f} MPa")
        print(f"  caisson suspendu : {pp['box']['total_kg']:.1f} kg ; manchon Ø80 : poussée {pp['sleeve']['thrust_N']:.1f} N ; "
              f"membrane (A) : T = {pp['membrane_A']['tension_N_m']:.1f} N/m")
    RES.mkdir(parents=True, exist_ok=True)
    (RES / "frame.json").write_text(json.dumps(out, indent=1, default=float, ensure_ascii=False))
    # figure : géométrie + 1er mode (référence 3 faces)
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fr, feet = build("reference", "3faces", 0.25)
    f, V = fr.modes(feet, nmodes=4)
    fig = plt.figure(figsize=(10, 4.5))
    for k in range(2):
        ax = fig.add_subplot(1, 2, k + 1, projection="3d")
        nn = len(fr.nodes)
        U = V[:6 * nn, k].reshape(nn, 6)[:, :3]
        sc = 0.08 / max(np.abs(U).max(), 1e-12)
        for e in fr.elems:
            p1, p2 = fr.nodes[e["n"][0]], fr.nodes[e["n"][1]]
            ax.plot(*zip(p1, p2), color="0.7", lw=1)
            q1, q2 = p1 + sc * U[e["n"][0]], p2 + sc * U[e["n"][1]]
            ax.plot(*zip(q1, q2), color="C0", lw=1.5)
        ax.set_title(f"mode {k+1} : {f[k]:.0f} Hz ({mode_label(fr, V[:, k])})", fontsize=9)
        ax.set_box_aspect((1, 1, 1.4))
    fig.suptitle("Bâti de référence (Rexroth 45×90 / 45×45, écharpes sur 3 faces, assemblages semi-rigides)", fontsize=10)
    fig.tight_layout(); fig.savefig(FIG / "frame_modes.png", dpi=120); plt.close(fig)
    if verbose:
        print("→ results/frame.json, figures/frame_modes.png")
    return out


if __name__ == "__main__":
    run()
