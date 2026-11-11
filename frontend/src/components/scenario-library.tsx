"use client";
import { useMemo, useState } from "react";
import Link from "next/link";
import { useDashboard } from "./dashboard-shell";
import type { CopyKey } from "@/lib/dashboard-copy";
import type { ScenarioEpisode, ScenarioNote, ScenarioVerdict } from "@/lib/dashboard-types";

const categoryCopy: Record<string, CopyKey> = {
 macro: "catMacro", earnings: "catEarnings", monetary: "catMonetary", trade: "catTrade", foreign_markets: "catForeignMarkets",
 military: "catMilitary", elections: "catElections", taxes: "catTaxes", unclassified: "catUnclassified",
};
const verdictCopy: Record<ScenarioVerdict, CopyKey> = { warned: "verdictWarned", borderline: "verdictBorderline", missed: "verdictMissed", no_data: "verdictNoData" };
const geoCopy: Record<ScenarioEpisode["geo"], CopyKey> = { foreign: "geoForeign", domestic: "geoDomestic", both: "geoBoth" };
const noteCopy: Record<ScenarioNote, CopyKey> = {
 price_missing: "notePriceMissing", window_incomplete: "noteWindowIncomplete", trough_at_window_end: "noteTroughEdge",
 source_unverified: "noteSourceUnverified", window_overlaps: "noteOverlaps",
};
const pct = (value: number | null | undefined, digits = 1) => typeof value === "number" && Number.isFinite(value) ? `${value > 0 ? "+" : ""}${(value * 100).toFixed(digits)}%` : "N/A";

function useScenarioLabels() {
 const { t, language } = useDashboard();
 const category = (id: string) => categoryCopy[id] ? t(categoryCopy[id]) : id;
 const text = (value: { en: string; ko: string }) => language === "en" ? value.en : value.ko;
 return { t, category, text, language };
}

function EpisodeCard({ episode, names }: { episode: ScenarioEpisode; names: Record<string, string> }) {
 const { t, category, text } = useScenarioLabels();
 const m = episode.metrics, model = episode.model;
 const sessions = (n: number | null | undefined) => typeof n === "number" ? `${n} ${t("scenarioSessions")}` : "N/A";
 const recovery = !m ? "N/A" : m.sessions_to_recover === null ? t("scenarioNotRecovered") : sessions(m.sessions_to_recover);
 return <article className={`scenario-card verdict-${model.verdict}`}>
  <div className="scenario-card-top"><time dateTime={episode.onset}>{episode.onset}</time><span className={`tag scenario-tier ${episode.tier}`}>{t(episode.tier === "core" ? "scenarioCore" : "scenarioSupporting")}</span></div>
  <h3>{text(episode.name)}</h3>
  <p className="scenario-meta"><span className="tag">{category(episode.category)}</span><span>{t(geoCopy[episode.geo])}</span></p>
  <p className="scenario-cause">{text(episode.cause)}</p>
  {episode.category_note && <p className="scenario-category-note">{text(episode.category_note)}</p>}
  <dl className="scenario-metrics">
   <div><dt>{t("scenarioOnset")}</dt><dd className={m ? "negative" : undefined}>{pct(m?.onset_return)}</dd></div>
   <div><dt>{t("scenarioMaxDd")}</dt><dd className={m ? "negative" : undefined}>{pct(m?.max_drawdown)}</dd></div>
   <div><dt>{t("scenarioToTrough")}</dt><dd>{sessions(m?.sessions_to_trough)}</dd></div>
   <div><dt>{t("scenarioRecovery")}</dt><dd>{recovery}</dd></div>
  </dl>
  <div className="scenario-model">
   <span><small>{t("scenarioPriorV1")}</small><b>{model.prior_risk === null ? "N/A" : `${(model.prior_risk * 100).toFixed(1)}%`}</b><em className={`verdict ${model.verdict}`}>{t(verdictCopy[model.verdict])}</em></span>
   <span><small>{t("scenarioMsi")}</small><b>{model.msi === null ? "N/A" : model.msi.toFixed(3)}</b><em>{model.msi_recognized === null ? t("verdictNoData") : t(model.msi_recognized ? "scenarioMsiYes" : "scenarioMsiNo")}</em></span>
  </div>
  {(episode.notes.length > 0 || (model.origin && model.origin !== "historical_oos")) && <ul className="scenario-notes">
   {model.origin && model.origin !== "historical_oos" && <li>{t("scenarioOriginNote")}</li>}
   {episode.notes.map(note => <li key={note}>{t(noteCopy[note])}{note === "window_overlaps" && ` ${episode.overlaps.map(id => names[id] ?? id).join(", ")}`}</li>)}
  </ul>}
  {episode.source && <a className="text-link scenario-source" href={episode.source.url} target="_blank" rel="noopener noreferrer">{t("scenarioSource")} · {episode.source.title} ↗</a>}
 </article>;
}

export function ScenarioLibrary() {
 const { scenarios } = useDashboard();
 const { t, category, language } = useScenarioLabels();
 const [filter, setFilter] = useState("all");
 const [sort, setSort] = useState<"date" | "drawdown">("date");
 const [showAll, setShowAll] = useState(false);
 const names = useMemo(() => Object.fromEntries((scenarios?.episodes ?? []).map(e => [e.id, `${e.onset} ${language === "en" ? e.name.en : e.name.ko}`])), [scenarios, language]);
 const visible = useMemo(() => {
  const rows = (scenarios?.episodes ?? []).filter(e => (filter === "all" || e.category === filter) && (showAll || e.tier === "core"));
  return [...rows].sort((a, b) => sort === "date"
   ? b.onset.localeCompare(a.onset)
   : (a.metrics?.max_drawdown ?? 0) - (b.metrics?.max_drawdown ?? 0));
 }, [scenarios, filter, sort, showAll]);
 const hidden = showAll ? 0 : (scenarios?.episodes ?? []).filter(e => (filter === "all" || e.category === filter) && e.tier !== "core").length;
 if (!scenarios) return <section className="panel empty-state"><h2>{t("scenarioTitle")}</h2><p>{t("scenarioUnavailable")}</p></section>;
 return <section className="panel scenario-library" aria-labelledby="scenario-library-title">
  <div className="panel-header"><h2 id="scenario-library-title">{t("scenarioTitle")}</h2><span className="tag">{t("scenarioTag")}</span></div>
  <p className="scope-label">{t("scenarioScope")} · {scenarios.episodes.length}{language === "en" ? " " : ""}{t("scenarioEpisodes")} · {t("scenarioPriceAsOf")} {scenarios.asOf}</p>
  <h3 className="scenario-subheading">{t("scenarioByCategory")}</h3>
  <div className="table-scroll"><table className="scenario-summary">
   <thead><tr><th scope="col">{t("scenarioCategory")}</th><th scope="col">{t("scenarioCount")}</th><th scope="col">{t("scenarioMedianDd")}</th><th scope="col">{t("scenarioWorstDd")}</th><th scope="col">{t("scenarioWarned")}</th></tr></thead>
   <tbody>{scenarios.summary.map(row => <tr key={row.category} className={filter === row.category ? "selected" : ""}>
    <th scope="row"><button type="button" className="link-button" onClick={() => setFilter(filter === row.category ? "all" : row.category)} aria-pressed={filter === row.category}>{category(row.category)}</button></th>
    <td>{row.episodes}</td><td>{pct(row.median_max_drawdown)}</td><td>{pct(row.worst_max_drawdown)}</td><td>{row.judged ? `${row.warned} / ${row.judged}` : "N/A"}</td>
   </tr>)}</tbody>
  </table></div>
  <div className="scenario-controls">
   <div className="small-toggle scenario-filter" role="group" aria-label={t("scenarioFilter")}>
    <button type="button" aria-pressed={filter === "all"} onClick={() => setFilter("all")}>{t("scenarioAll")}</button>
    {scenarios.summary.map(row => <button type="button" key={row.category} aria-pressed={filter === row.category} onClick={() => setFilter(row.category)}>{category(row.category)}</button>)}
   </div>
   <label className="field-label scenario-sort">{t("scenarioSort")}<select value={sort} onChange={e => setSort(e.target.value as "date" | "drawdown")}><option value="date">{t("scenarioSortDate")}</option><option value="drawdown">{t("scenarioSortDd")}</option></select></label>
  </div>
  {visible.length === 0 ? (hidden === 0 && <p className="panel-note">{t("scenarioEmpty")}</p>) : <div className="scenario-grid">{visible.map(e => <EpisodeCard key={e.id} episode={e} names={names}/>)}</div>}
  {(hidden > 0 || showAll) && <p className="scenario-more"><button type="button" className="link-button" aria-expanded={showAll} onClick={() => setShowAll(!showAll)}>{showAll ? t("scenarioShowCore") : `${t("scenarioShowAll")} (+${hidden})`}</button></p>}
  <p className="panel-note">{t("scenarioMethod")}</p>
  <p className="panel-note">{t("scenarioTaxonomy")} <a className="text-link" href={scenarios.taxonomy.url} target="_blank" rel="noopener noreferrer">NBER w28687 ↗</a></p>
 </section>;
}

export function ScenarioLinkPanel() {
 const { scenarios } = useDashboard();
 const { t } = useScenarioLabels();
 if (!scenarios) return null;
 const judged = scenarios.episodes.filter(e => e.model.verdict !== "no_data");
 const warned = judged.filter(e => e.model.verdict === "warned").length;
 return <section className="panel scenario-link-panel">
  <div className="panel-header"><h2>{t("scenarioTitle")}</h2><Link className="text-link" href="/cases">{t("scenarioLinkCta")} →</Link></div>
  <p>{t("scenarioLinkText")}</p>
  <dl><div><dt>{t("scenarioCount")}</dt><dd>{scenarios.episodes.length}</dd></div><div><dt>{t("scenarioWarned")}</dt><dd>{warned} / {judged.length}</dd></div><div><dt>{t("scenarioPriceAsOf")}</dt><dd>{scenarios.asOf}</dd></div></dl>
 </section>;
}
