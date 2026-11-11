import hashlib
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from qsignals.calendar import latest_closed_session, load_sessions
from qsignals.import_scores import SOURCE_FILES, import_data, load_source
from qsignals.prices import parse_prices
from qsignals.scores import build_rows, read_scores

ROOT = Path(__file__).resolve().parent.parent


def payloads():
    days = [d for d in load_sessions() if d >= "2026-01-02"][:7]
    points = [{"date": day, "price": 100.0, "risk": .2, "msi": 0., "threshold": 1.} for day in days[:6]]
    ops = {"date": days[-1], "risk": .3, "msi": .1, "threshold": 1., "recordType": "OPERATIONAL"}
    return days, {"global_markets": {"korea": points}, "operational_markets": {"markets": {"korea": {"history": [ops]}}}}


def xml_prices(days, close="100"):
    return ('<protocol><chartdata symbol="KPI200" timeframe="day">' + ''.join(
        f'<item data="{day.replace("-", "")}|100|110|90|{close}|1000"/>' for day in days
    ) + '</chartdata></protocol>').encode()


class PriceAndImportTest(unittest.TestCase):
    def test_prices_enrich_without_changing_scores(self):
        days, data = payloads()
        prices = {day: 100. for day in days}
        old = build_rows(data["global_markets"], data["operational_markets"])
        new = build_rows(data["global_markets"], data["operational_markets"], prices)
        for a, b in zip(old, new):
            self.assertEqual((a.risk_v1,a.msi,a.stress_threshold,a.record_type), (b.risk_v1,b.msi,b.stress_threshold,b.record_type))
        self.assertEqual(new[-1].kospi200_close, 100.)

    def test_duplicate_source_dates_rejected_before_merging(self):
        _, data = payloads()
        data["global_markets"]["korea"].append(data["global_markets"]["korea"][-1])
        with self.assertRaises(ValueError):
            build_rows(data["global_markets"],data["operational_markets"])
        _, data = payloads()
        data["operational_markets"]["markets"]["korea"]["history"] *= 2
        with self.assertRaises(ValueError):
            build_rows(data["global_markets"],data["operational_markets"])

    def test_wrong_index_missing_session_and_invalid_close_rejected(self):
        days, _ = payloads()
        good = xml_prices(days)
        self.assertEqual(len(parse_prices(good, days[-1])), 7)
        for raw in [good.replace(b'KPI200',b'KOSPI'), xml_prices(days[:2]+days[3:]),
                    xml_prices(days, 'NaN'), xml_prices(days, '-1'), xml_prices(days+days[-1:])]:
            with self.subTest(raw=raw[:80]), self.assertRaises(ValueError):
                parse_prices(raw,days[-1])

    def test_price_reference_disagreement_is_rejected(self):
        days,data=payloads()
        with self.assertRaisesRegex(ValueError,'disagrees'):
            build_rows(data['global_markets'],data['operational_markets'],{days[0]:101.})

    def test_failed_refresh_preserves_prior_files(self):
        days,data=payloads()
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'korea_scores.csv';p.write_text('prior good data')
            with patch('qsignals.import_scores.fetch_prices',side_effect=ValueError('missing session')):
                with self.assertRaises(ValueError):import_data(data,{}, {},temp)
            self.assertEqual(p.read_text(),'prior good data')

    def test_remote_files_are_read_at_one_pinned_commit(self):
        _, data=payloads();sha='a'*40;seen=[]
        def download(url):
            seen.append(url)
            if '/commits/main' in url:return json.dumps({'sha':sha}).encode()
            for key,path in SOURCE_FILES.items():
                if url.endswith(path):return json.dumps(data[key]).encode()
            raise AssertionError(url)
        with patch('qsignals.import_scores._download',side_effect=download):
            _,_,source=load_source()
        self.assertEqual(source['source_git_commit'],sha)
        self.assertTrue(all('/'+sha+'/' in url for url in seen[1:]))

    def test_calendar_includes_official_additional_closures(self):
        sessions=load_sessions()
        self.assertNotIn('2026-06-03',sessions)
        self.assertNotIn('2026-07-17',sessions)
        self.assertIn('2026-07-16',sessions)

    def test_publication_deadline_and_holiday_are_distinct_from_missing_data(self):
        # 12:29 UTC = 21:29 KST; the six-hour source deadline has not passed.
        self.assertEqual(latest_closed_session(datetime(2026,11,10,12,29,tzinfo=timezone.utc),6),'2026-11-09')
        self.assertEqual(latest_closed_session(datetime(2026,11,10,12,30,tzinfo=timezone.utc),6),'2026-11-10')
        self.assertEqual(latest_closed_session(datetime(2026,7,17,14,tzinfo=timezone.utc),6),'2026-07-16')

    def test_identical_refresh_keeps_original_provenance(self):
        days,data=payloads();raw=xml_prices(days)
        price_meta={'provider':'test','sha256':hashlib.sha256(raw).hexdigest(),'last_date':days[-1],'retrieved_at':'first'}
        prices={day:100. for day in days}
        with tempfile.TemporaryDirectory() as temp, patch('qsignals.import_scores.latest_closed_session',return_value=days[-1]):
            with patch('qsignals.import_scores.fetch_prices',return_value=(prices,raw,price_meta)):
                first=import_data(data,{}, {},temp)
            with patch('qsignals.import_scores.fetch_prices',return_value=(prices,raw,{**price_meta,'retrieved_at':'second'})):
                second=import_data(data,{}, {},temp)
            self.assertEqual(first,second)

    def test_event_report_has_separate_source_quality_column(self):
        from qsignals.events import read_events
        from qsignals.diagnostics import diagnose_all
        from qsignals.report import render_markdown
        rows=read_scores(ROOT/'data/input/korea_scores.csv')
        events=read_events(ROOT/'data/events/kospi_2026_events.csv')
        provenance=json.loads((ROOT/'data/input/provenance.json').read_text())
        md=render_markdown(events,diagnose_all(events,rows),rows,provenance,'2026-01-01')
        block=md.split('## 이벤트별 결과')[1].split('## 트리거')[0]
        table=[line for line in block.splitlines() if line.startswith('|')]
        self.assertTrue(all(line.count('|')==11 for line in table))

    def test_bundled_inputs_match_declared_coverage(self):
        rows=read_scores(ROOT/'data/input/korea_scores.csv')
        p=json.loads((ROOT/'data/input/provenance.json').read_text())
        self.assertEqual(hashlib.sha256((ROOT/'data/input/korea_scores.csv').read_bytes()).hexdigest(),p['scores_sha256'])
        expected={day for day in load_sessions() if rows[0].date<=day<=rows[-1].date}
        self.assertEqual(sorted(expected-{r.date for r in rows}),p['missing_sessions'])
        self.assertEqual(max(r.date for r in rows if r.risk_v1 is not None),p['last_risk_date'])
        self.assertEqual(max(r.date for r in rows if r.kospi200_close is not None),p['last_price_date'])


if __name__=='__main__':unittest.main()
