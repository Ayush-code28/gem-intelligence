import type { ReactNode } from 'react'
import { PageHeader } from '../components/Layout'

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="card p-5">
      <h2 className="text-lg font-semibold text-ink">{title}</h2>
      <div className="mt-2 space-y-2 text-slate-700">{children}</div>
    </section>
  )
}

export function AboutPage() {
  return (
    <>
      <PageHeader title="About & data policy" description="What this site is, where its information comes from, and its limitations." />
      <div className="grid gap-5 lg:grid-cols-2">
        <Section title="An independent dashboard — not the GeM portal">
          <p>
            This website is operated independently. It is <strong>not</strong> the Government e-Marketplace (GeM), is not
            affiliated with or endorsed by GeM SPV, the Ministry of Commerce &amp; Industry or the Government of India,
            and cannot be used to bid, register or transact.
          </p>
          <p>
            The official portal is <span className="font-mono">gem.gov.in</span>. Type that address yourself, never enter
            GeM credentials on any other site, and be cautious of look-alike websites.
          </p>
        </Section>
        <Section title="Source of the information">
          <p>
            Listings are copied from publicly accessible listing pages of the GeM portal (BidPlus “All Bids”), only when the
            operator has the access and permissions this requires. Each listing links to its official page, which opens in a
            new window; GeM pages are never embedded.
          </p>
          <p>Only the fields shown are collected: title, buyer organisation, category, listing type, quantity, bid start, deadline and the official link.</p>
        </Section>
        <Section title="Data origin labels">
          <p>Every record states how it entered this site:</p>
          <ul className="list-disc space-y-1 pl-5">
            <li>
              <strong>Live-collected</strong> — fetched automatically from the official portal by this site’s collector.
            </li>
            <li>
              <strong>Imported</strong> — loaded from a file by the site operator. This site has not collected or verified it.
            </li>
            <li>
              <strong>Synthetic demo</strong> — invented data used to demonstrate and test the site, titled “[SYNTHETIC]”. It is
              never a real listing and never links to GeM.
            </li>
          </ul>
          <p>The freshness indicator only counts live collection; file imports are shown separately.</p>
        </Section>
        <Section title="Collection frequency">
          <p>
            A collector runs once a day, scheduled for 01:00 UTC (06:30 IST). Scheduled jobs can start late or fail, so the
            dashboard always shows the time of the <em>last successful</em> collection rather than the planned schedule, and
            warns when data is more than 36 hours old.
          </p>
        </Section>
        <Section title="Limitations">
          <ul className="list-disc space-y-1 pl-5">
            <li>Data can be up to a day old, or older if a run fails. Deadlines may have been extended or bids cancelled since.</li>
            <li>Collection is incremental and capped, so not every listing on GeM is necessarily present.</li>
            <li>A listing that is no longer seen is never marked as removed — absence from one scan is not evidence of withdrawal.</li>
            <li>Missing fields are shown as “Not available” and are never estimated. Times are shown in India Standard Time.</li>
          </ul>
        </Section>
        <Section title="Always verify on the official source">
          <p>
            Before acting on any listing, open it on the GeM portal and read the official bid document, corrigenda and terms.
            Information here is provided as-is, without warranty, and must not be relied on as the official record.
          </p>
        </Section>
        <Section title="Rights">
          <p>
            Listing content belongs to its publishers. GeM’s copyright policy requires prior written permission from GeM SPV
            to reproduce its content; this site displays GeM data only once that permission has been obtained. GeM names and
            marks are not used as branding here.
          </p>
        </Section>
      </div>
    </>
  )
}
