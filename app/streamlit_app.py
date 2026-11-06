"""Application interactive de planification — bonus B6.

Interface "user-friendly" permettant à un planificateur Maghreb Steel (non
technique) de :
    - modifier le carnet de commandes (éditeur de tableau) ;
    - régler les options du modèle (règle galva, stocks, retards, campagnes,
      prix du HRC) ;
    - relancer l'optimisation et lire immédiatement le plan de marche, les
      goulots, les commandes refusées et leur contrainte bloquante.

Lancement :  streamlit run app/streamlit_app.py
"""
from __future__ import annotations

import copy
import io
import sys
from pathlib import Path

import pandas as pd
import altair as alt
import streamlit as st

# Rendre le package src importable quel que soit le dossier de lancement.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src import config, reporting
from src.data_loader import Data, Order, load_data
from src.solve import run
from src.validation import validate


st.set_page_config(page_title="Maghreb Steel | Production Planning Optimisation",
                   page_icon="🏭", layout="wide", initial_sidebar_state="collapsed")
theme_path = ROOT / "app" / "maghreb_steel_theme.css"
if theme_path.is_file():
    st.markdown("<style>" + theme_path.read_text(encoding="utf-8") + "</style>", unsafe_allow_html=True)


# --------------------------------------------------------------------------
# Données : chargées une fois et mises en cache
# --------------------------------------------------------------------------
@st.cache_data(show_spinner=False)
def _base_orders_df() -> pd.DataFrame:
    d = load_data()
    return pd.DataFrame([{
        "id": o.id, "client": o.client, "famille": o.famille, "grade": o.grade,
        "ep": o.ep, "larg": o.larg, "ton": o.ton, "prix": o.prix,
        "sem": o.sem, "prio": o.prio,
    } for o in d.orders])


@st.cache_resource(show_spinner=False)
def _base_data() -> Data:
    return load_data()


def _data_from_df(df: pd.DataFrame) -> Data:
    """Reconstruit un objet Data à partir du carnet édité (sans re-sanity)."""
    d = copy.deepcopy(_base_data())
    orders = []
    for _, r in df.iterrows():
        if not str(r["id"]).strip():
            continue
        orders.append(Order(
            id=str(r["id"]), client=str(r["client"]), famille=str(r["famille"]),
            grade=str(r["grade"]), ep=float(r["ep"]), larg=int(r["larg"]),
            ton=float(r["ton"]), prix=float(r["prix"]), sem=int(r["sem"]),
            prio=str(r["prio"]),
        ))
    d.orders = orders
    return d


# --------------------------------------------------------------------------
# En-tête
# --------------------------------------------------------------------------
st.markdown(
    """
    <section class="ms-banner">
      <div class="ms-banner-copy">
        <div class="ms-eyebrow">OPERATIONS RESEARCH / INDUSTRIAL DECISION INTELLIGENCE</div>
        <h1>Production Planning <em>Optimisation</em></h1>
        <p>Optimisation commandes × capacité · Usine de Tit Mellil · Horizon de 4 semaines</p>
        <span class="ms-banner-tag">◆ &nbsp; Maghreb Steel case study · EMINES / UM6P</span>
      </div>
      <div class="ms-logo-panel">
        <div class="ms-logo-wordmark" role="img" aria-label="Maghreb Steel">
          <span class="ms-logo-mark"><i></i><b></b></span>
          <span class="ms-logo-name">MAGHREB <strong>STEEL</strong></span>
        </div>
      </div>
    </section>
    """,
    unsafe_allow_html=True,
)

# --------------------------------------------------------------------------
# Barre latérale : options du modèle
# --------------------------------------------------------------------------
with st.sidebar:
    st.header("⚙️ Options du modèle")
    objectif = st.radio("🎯 Objectif", ["marge", "nb_commandes"],
                        format_func=lambda o: "Maximiser la marge (O1)" if o == "marge"
                        else "Maximiser le nb de commandes",
                        help="O1 de l'énoncé (marge) ou maximisation du "
                             "nombre de commandes honorées (MILP accept/reject).")
    galva = st.checkbox("Règle galva HDG (ep≤seuil→LGA)", value=True,
                        help="Hypothèse hors note de cadrage : fige LGA/LGB du HDG selon l'épaisseur.")
    seuil = st.slider("Seuil galva (mm)", 0.3, 1.0, 0.6, 0.05, disabled=not galva)
    stocks = st.checkbox("Stocks produits finis (E8)", value=True)
    enforce_min = st.checkbox("Imposer le stock de sécurité min", value=True,
                              disabled=not stocks)
    inclure_pk = st.checkbox("Stock PK qualifié par grade", value=True,
                             help="Ajoute le stock PK décapé (par grade, net du min sécurité) "
                                  "à la matière disponible, en plus de la dispo HRC.")
    retards = st.checkbox("Autoriser les retards (B2)", value=False)
    stockage = st.checkbox("Coûts de stockage (B3)", value=False)
    campagnes = st.checkbox("Campagnes / MILP (B4)", value=False)
    qmin = st.slider("Tonnage min de campagne (T)", 0, 1500, 100, 50,
                     disabled=not campagnes)
    hrc_mult = st.slider("Variation prix HRC (%)", -20, 30, 0, 5,
                         help="Scénario type E20 (HRC plus cher / moins cher).")
    st.divider()
    lancer = st.button("▶️ Lancer l'optimisation", type="primary", width="stretch")


# --------------------------------------------------------------------------
# Carnet de commandes éditable
# --------------------------------------------------------------------------
workspace_tabs = st.tabs(["▦  Vue d’ensemble", "☷  Carnet de commandes", "▤  Analyses détaillées"])

with workspace_tabs[0]:
    st.caption("Modifiez les options dans le panneau latéral ou le carnet de commandes, puis relancez le solveur.")
    lancer = st.button("▶  Recalculer le plan optimal", key="dashboard_run", type="primary") or lancer

with workspace_tabs[1]:
    st.subheader("📋 Carnet de commandes (éditable)")
    st.caption("Modifiez les tonnages, prix, semaines… ajoutez ou supprimez des lignes, "
               "puis cliquez sur « Lancer l'optimisation ».")
    if "orders_df" not in st.session_state:
        st.session_state.orders_df = _base_orders_df()

    col_a, col_b = st.columns([1, 1])
    with col_a:
        if st.button("↺ Réinitialiser le carnet d'origine"):
            st.session_state.orders_df = _base_orders_df()
    with col_b:
        st.metric("Lignes dans le carnet", len(st.session_state.orders_df))

    edited = st.data_editor(st.session_state.orders_df, num_rows="dynamic",
                            width="stretch", height=280, key="editor")



# --------------------------------------------------------------------------
# Résolution + affichage
# --------------------------------------------------------------------------
def _options() -> config.ModelOptions:
    return config.ModelOptions(
        objectif=objectif,
        galva_rule_hdg=galva, galva_seuil_mm=seuil,
        stocks_pf=stocks, enforce_stock_min=enforce_min,
        inclure_stock_pk=inclure_pk,
        retards_autorises=retards, cout_stockage=stockage,
        campagnes=campagnes, q_min_campagne=float(qmin),
    )


def _plan_excel_bytes(sol) -> bytes:
    """Sérialise le plan de marche complet en classeur Excel (téléchargeable)."""
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xl:
        reporting.plan_de_marche_famille(sol).to_excel(xl, sheet_name="Plan_famille")
        reporting.plan_de_marche_ligne(sol).to_excel(xl, sheet_name="Charge_ligne")
        reporting.utilisation_table(sol).to_excel(xl, sheet_name="Utilisation")
        reporting.marge_par_famille(sol).to_excel(xl, sheet_name="Marge_famille", index=False)
        reporting.commandes_refusees(sol).to_excel(xl, sheet_name="Refus", index=False)
        if not sol.is_mip:
            reporting.shadow_ressources(sol).to_excel(xl, sheet_name="ShadowPrices", index=False)
    return buf.getvalue()


# Populate the portfolio dashboard with a baseline optimization on first load.
# Subsequent runs use the edited order book and the sidebar options.
if "sol" not in st.session_state:
    try:
        initial_data = _base_data()
        initial_options = config.ModelOptions()
        initial_solution = run(initial_data, initial_options)
        st.session_state["sol"] = initial_solution
        st.session_state["rep"] = validate(initial_data, initial_solution.x, initial_options)
    except Exception as exc:
        st.session_state["sol"] = None
        st.session_state["rep"] = None
        st.session_state["baseline_warning"] = str(exc)

if lancer:
    st.session_state.orders_df = edited
    data = _data_from_df(edited)
    if hrc_mult != 0:
        data.prix_hrc = {k: v * (1 + hrc_mult / 100.0) for k, v in data.prix_hrc.items()}
    opt = _options()
    with st.spinner("Résolution du programme linéaire (CBC)…"):
        sol = run(data, opt)
        rep = validate(data, sol.x, opt)
    st.session_state["sol"] = sol      # on persiste pour que l'UI survive aux reruns
    st.session_state["rep"] = rep

sol = st.session_state.get("sol")
rep = st.session_state.get("rep")

with workspace_tabs[0]:
    st.markdown('<div class="ms-subhead"><strong>Tableau de bord de production</strong><span>OPTIMISATION · CAPACITÉ · MARGE</span></div>', unsafe_allow_html=True)
    if sol is not None and sol.status == "Optimal":
        k = reporting.kpis(sol)
        a,b,c,d = st.columns(4)
        a.metric("Marge totale", f"{k['marge_totale_MAD']/1e6:.2f} MMAD")
        b.metric("Taux de service", f"{k['taux_service_pct']:.1f} %")
        c.metric("Marge moyenne", f"{k['marge_moyenne_MAD_par_T']:,.0f} MAD/T")
        d.metric("Commandes refusées", str(k["commandes_refus_total"]))
        chart_a, chart_b = st.columns(2, gap="medium")
        with chart_a:
            with st.container(border=True):
                st.markdown("**Utilisation des lignes de production**")
                util = reporting.utilisation_table(sol).reset_index().rename(columns={"index":"Ligne"})
                util_long = util.melt(id_vars="Ligne", var_name="Semaine", value_name="Utilisation")
                heat = alt.Chart(util_long).mark_rect(cornerRadius=3).encode(
                    x=alt.X("Semaine:N", title="Semaine", sort=["S1","S2","S3","S4"]),
                    y=alt.Y("Ligne:N", title=None),
                    color=alt.Color("Utilisation:Q", scale=alt.Scale(domain=[0,100],range=["#e7eff5","#ecac48"]), title="Charge (%)"),
                    tooltip=["Ligne:N","Semaine:N",alt.Tooltip("Utilisation:Q",format=".0f",title="Charge %")]
                ).properties(height=205)
                st.altair_chart(heat, use_container_width=True)
        with chart_b:
            with st.container(border=True):
                st.markdown("**Marge par famille de produits**")
                margins = reporting.marge_par_famille(sol)
                bars = alt.Chart(margins).mark_bar(cornerRadiusEnd=4,color="#d9454b").encode(
                    x=alt.X("Famille:N",sort="-y",axis=alt.Axis(labelAngle=0),title=None),
                    y=alt.Y("Marge_MAD:Q", title="Marge (MAD)"),
                    tooltip=["Famille:N",alt.Tooltip("Marge_MAD:Q",format=",.0f"),alt.Tooltip("Tonnage_T:Q",format=",.0f")]
                ).properties(height=205)
                st.altair_chart(bars, use_container_width=True)
        chart_c, chart_d = st.columns(2, gap="medium")
        with chart_c:
            with st.container(border=True):
                st.markdown("**Plan de production · semaines 1–4**")
                plan = reporting.plan_de_marche_famille(sol).drop(index="TOTAL",errors="ignore")
                weekly = plan[[x for x in ("S1","S2","S3","S4") if x in plan.columns]].sum().reset_index()
                weekly.columns = ["Semaine","Tonnage"]
                figure = alt.Chart(weekly).mark_area(line={"color":"#143f60","strokeWidth":3},color="#a9c2d5",opacity=.65).encode(
                    x=alt.X("Semaine:N",sort=["S1","S2","S3","S4"],title=None),
                    y=alt.Y("Tonnage:Q",title="Tonnes"),tooltip=["Semaine:N",alt.Tooltip("Tonnage:Q",format=",.0f")]
                ).properties(height=175)
                st.altair_chart(figure,use_container_width=True)
        with chart_d:
            with st.container(border=True):
                st.markdown("**Synthèse du carnet de commandes**")
                families = edited.groupby("famille",dropna=False)["ton"].sum().reset_index()
                fam_chart = alt.Chart(families).mark_bar(cornerRadiusEnd=4,color="#e5a342").encode(
                    x=alt.X("famille:N",title=None,axis=alt.Axis(labelAngle=0)),
                    y=alt.Y("ton:Q",title="Tonnage demandé"),
                    tooltip=["famille:N",alt.Tooltip("ton:Q",format=",.0f")]
                ).properties(height=175)
                st.altair_chart(fam_chart,use_container_width=True)
        st.caption("Résultats calculés par le solveur PuLP/CBC. Modifiez le carnet ou les paramètres puis relancez l’optimisation.")
    else:
        x,y,z = st.columns(3)
        x.metric("Commandes dans le carnet",len(edited))
        y.metric("Tonnage demandé",f"{pd.to_numeric(edited['ton'],errors='coerce').sum():,.0f} T")
        z.metric("Horizon","4 semaines")
        st.info("Lancez l’optimisation depuis le panneau latéral pour afficher les résultats et les graphiques.")
        if "baseline_warning" in st.session_state:
            st.caption("Le calcul initial n’a pas pu être effectué : " + st.session_state["baseline_warning"])
    st.markdown('<div class="ms-note">Étude académique indépendante fondée sur un cas industriel Maghreb Steel. Les simulations ne constituent pas des résultats opérationnels validés par l’entreprise.</div>',unsafe_allow_html=True)

with workspace_tabs[2]:
    if sol is None:
        st.info("Réglez les options puis cliquez sur **« Lancer l'optimisation »** "
                "dans la barre latérale.")
    elif sol.status != "Optimal":
        st.error(f"Statut du solveur : {sol.status} — le problème n'a pas d'optimum.")
    else:
        k = reporting.kpis(sol)
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Marge totale", f"{k['marge_totale_MAD']/1e6:.2f} MMAD")
        c2.metric("Taux de service", f"{k['taux_service_pct']:.1f} %")
        c3.metric("Marge moyenne", f"{k['marge_moyenne_MAD_par_T']:.0f} MAD/T")
        c4.metric("Refus (total/partiel)",
                  f"{k['commandes_refus_total']} / {k['commandes_partielles']}")

        ok = "✅ Toutes les contraintes vérifiées (validation indépendante)" if rep.all_ok \
            else "❌ Violation détectée par la validation indépendante !"
        (st.success if rep.all_ok else st.error)(ok)

        st.download_button("⬇️ Télécharger le plan de marche (Excel)",
                           data=_plan_excel_bytes(sol), file_name="plan_de_marche.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

        tabs = st.tabs(["📅 Plan de marche", "📊 Utilisation lignes",
                        "💰 Marge par famille", "💎 Shadow prices",
                        "🚫 Commandes refusées", "🧮 Prix plancher (B1)"])
        with tabs[0]:
            st.dataframe(reporting.plan_de_marche_famille(sol), width="stretch")
            st.caption("Tonnage fini produit par famille × semaine.")
        with tabs[1]:
            util = reporting.utilisation_table(sol)
            st.dataframe(util.style.background_gradient(cmap="YlOrRd", vmin=0, vmax=100)
                         .format("{:.0f}"), width="stretch")
            g = reporting.goulots(sol)
            st.caption("Goulots (≥99 %) : " +
                       (", ".join(f"{L} S{t}" for L, t, _ in g) or "aucun"))
        with tabs[2]:
            st.dataframe(reporting.marge_par_famille(sol), width="stretch",
                         hide_index=True)
            plus, moins = reporting.commandes_extremes(sol)
            if plus:
                st.write(f"**Plus rentable honorée** : {plus['ID']} "
                         f"({plus['Famille']} {plus['Grade']}, {plus['MargeU']:.0f} MAD/T)")
                st.write(f"**Moins rentable honorée** : {moins['ID']} "
                         f"({moins['Famille']} {moins['Grade']}, {moins['MargeU']:.0f} MAD/T)")
        with tabs[3]:
            if sol.is_mip:
                st.info("Shadow prices indisponibles en variante MILP (campagnes).")
            else:
                st.dataframe(reporting.shadow_ressources(sol), width="stretch",
                             hide_index=True)
                st.caption("Valeur marginale d'une unité de ressource saturée "
                           "(MAD/jour pour la capacité, MAD/T pour le HRC).")
        with tabs[4]:
            refus = reporting.commandes_refusees(sol)
            if refus.empty:
                st.success("Toutes les commandes sont honorées intégralement.")
            else:
                st.dataframe(refus, width="stretch", hide_index=True)
                st.caption("Contrainte bloquante tracée depuis les valeurs duales "
                           "(coût d'opportunité des ressources saturées).")
        with tabs[5]:
            st.caption("**Prix de vente minimal** (MAD/T) pour qu'une nouvelle commande soit "
                       "rentable, compte tenu des ressources saturées. Au-dessus de ce prix : "
                       "à accepter ; en dessous : à refuser ou renégocier.")
            if sol.is_mip:
                st.info("Les prix planchers nécessitent les shadow prices : utilisez "
                        "l'objectif « marge » (sans campagnes).")
            else:
                cps = st.number_input("Semaine de la consultation", 1, 4, 1)
                exemples = [("HDG", "DX51", 0.3, 1250), ("HDG", "DC01", 1.0, 1250),
                            ("PPGI", "DX51", 0.4, 1250), ("CRC", "S320", 0.4, 1100),
                            ("BACR", "DC01", 0.5, 1280), ("HRC DEC", "DC01", 3.0, 1320)]
                rows = []
                for fam, gr, ep, lg in exemples:
                    r = reporting.prix_plancher(sol, fam, gr, ep, lg, int(cps))
                    if r:
                        rows.append({"Famille": fam, "Grade": gr, "Ép.": ep, "Larg.": lg,
                                     "Prix plancher": r["prix_plancher"],
                                     "Coût de revient": r["cout_revient"],
                                     "Coût d'opportunité": r["cout_opportunite"],
                                     "Route": r["meilleure_route"]})
                st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
                st.caption("Prix plancher = coût de revient + coût d'opportunité des ressources "
                           "rares (= 0 si aucune ressource saturée n'est consommée).")


st.markdown('<div class="ms-license">Logo Maghreb Steel © Maghreb Steel, <a href="https://commons.wikimedia.org/wiki/File:Logo_-_Maghreb_Steel_(1).jpg" target="_blank">CC BY-SA 4.0 / Wikimedia Commons</a>. Projet académique indépendant — aucune affiliation officielle revendiquée.</div>',unsafe_allow_html=True)
