"""Bootable foundation screen; the expert cockpit is implemented in T12."""

import streamlit as st

st.set_page_config(page_title="AFS Spectroscopy Assistant", page_icon="🔬")
st.title("AFS Spectroscopy Design Assistant")
st.info("Das Projektfundament steht. Die fachliche Analyse wird in den nächsten Tickets umgesetzt.")
st.write(
    "Geplant: Kundenanfrage → Rückfragen → bedingte Methodenkandidaten "
    "mit Quellen → erster Machbarkeitsversuch."
)
st.caption("Aktueller Stand: Setup und Datenverträge. Noch keine Live-Analyse.")
