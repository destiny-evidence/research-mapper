/**
 * Veritas Health Innovation's privacy policy, transcribed. It is a legal
 * document: change it only to match the source, never to tidy it.
 */

const EFFECTIVE = "8 September 2026";
const UPDATED = "8 September 2026";

const Missing = ({ what }) => <span class="terms-unset">{what} not set</span>;

const PRIVACY_EMAIL = "privacy@futureevidence.org";

const BASES = [
  [
    "Providing and maintaining accounts/access",
    "Account data",
    "Performance of a contract",
  ],
  [
    "Product improvement and analytics",
    "Usage/analytics data",
    "Legitimate interests",
  ],
  [
    "Responding to feedback and improving features",
    "Feedback form data",
    "Legitimate interests",
  ],
  [
    "Security, fraud prevention, abuse monitoring",
    "Account and usage data",
    "Legitimate interests",
  ],
  [
    "Communicating service updates",
    "Account data (email)",
    "Performance of a contract / legitimate interests",
  ],
  ["Complying with legal obligations", "Account data", "Legal obligation"],
];

const List = ({ items }) => (
  <ul class="terms-list">
    {items.map((item) => (
      <li key={item}>{item}</li>
    ))}
  </ul>
);

const Section = ({ n, heading, children }) => (
  <section class="terms-section">
    <h2 class="policy-heading">
      {n}. {heading}
    </h2>
    {children}
  </section>
);

const Sub = ({ n, heading, children }) => (
  <div class="policy-sub">
    <h3 class="terms-heading">
      {n} {heading}
    </h3>
    {children}
  </div>
);

export function Privacy({ onBack }) {
  return (
    <div class="page policy">
      <button type="button" class="quiet" onClick={onBack}>
        Back to Research Mapper
      </button>

      <h1 class="policy-title">Privacy Policy</h1>
      <p class="policy-dates">
        Effective date: {EFFECTIVE ?? <Missing what="effective date" />} · Last
        updated: {UPDATED ?? <Missing what="last updated" />}
      </p>

      <p class="policy-text">
        Veritas Health Innovation Ltd (ABN 41 600 366 274) ("we", "us") operates
        evidence repository platforms, collectively the "Services" — that help
        technical advisors discover and use trustworthy evidence. This Privacy
        Policy explains what personal data we collect, why, and the rights users
        have over it.
      </p>
      <p class="policy-text">
        This policy applies to all Veritas Health Innovation services, unless a
        product states otherwise.
      </p>

      <Section n={1} heading="Who we are">
        <p class="policy-text">
          Veritas Health Innovation Ltd is the data controller for personal data
          processed through the Services.
        </p>
        <p class="policy-text">
          You can confidentially contact our Privacy Officer at:
        </p>
        <address class="policy-address">
          The Privacy Officer
          <br />
          Veritas Health Innovation Ltd
          <br />
          Level 5, 485 Latrobe Street, Melbourne 3000 Australia
          <br />
          Email: <a href={`mailto:${PRIVACY_EMAIL}`}>{PRIVACY_EMAIL}</a>
          <br />
          Website:{" "}
          <a
            href="https://www.futureevidence.org"
            target="_blank"
            rel="noreferrer"
          >
            www.futureevidence.org
          </a>
        </address>
      </Section>

      <Section n={2} heading="What data we collect">
        <Sub n="2.1" heading="Account data">
          <p class="policy-text">
            When someone registers or is provisioned an account, we collect:
          </p>
          <List
            items={[
              "Name and email address",
              "Login credentials (password stored as a hash, or SSO identifier)",
            ]}
          />
        </Sub>
        <Sub n="2.2" heading="Usage and analytics data">
          <p class="policy-text">
            To understand how the Services are used and improve them, we
            collect:
          </p>
          <List
            items={[
              "Pages and features accessed, search queries, clicks",
              "Session duration, timestamps, and frequency of use",
              "Device, browser type and geolocation",
              "Referring/exit pages",
            ]}
          />
          <p class="policy-text">
            We use this data in aggregate and at an individual level for product
            analytics; see Section 4.
          </p>
        </Sub>
        <Sub n="2.3" heading="Feedback form data">
          <p class="policy-text">
            Where a user chooses to submit feedback on features through an
            in-product form, we collect their name and email address along with
            the feedback content. We use this to follow up on feedback and to
            inform product improvements. We may use third-party form providers,
            such as Google Forms, to collect and store this information.
          </p>
        </Sub>
        <Sub n="2.4" heading="Data we do not currently collect">
          <p class="policy-text">
            The Services do not currently collect special category data (e.g.
            health, ethnicity) about account holders, nor do they knowingly
            collect data about children. If a specific repository begins
            collecting additional categories of data (e.g. uploaded documents
            containing personal data), this policy will be updated and users
            notified.
          </p>
        </Sub>
      </Section>

      <Section n={3} heading="How we collect data">
        <List
          items={[
            "Directly from the user (account registration, forms)",
            "Automatically through use of the Services (analytics tools, cookies, log files)",
            "From a partner or funder, where the user's organisation has requested an account be provisioned on their behalf",
          ]}
        />
      </Section>

      <Section n={4} heading="Why we use this data (purposes and legal basis)">
        <div class="policy-scroll">
          <table class="policy-table">
            <thead>
              <tr>
                <th>Purpose</th>
                <th>Data used</th>
                <th>Legal basis (GDPR)</th>
              </tr>
            </thead>
            <tbody>
              {BASES.map(([purpose, data, basis]) => (
                <tr key={purpose}>
                  <td>{purpose}</td>
                  <td>{data}</td>
                  <td>{basis}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p class="policy-text">
          Where we rely on legitimate interests, we've considered that this
          processing is proportionate and expected by users of a professional
          platform, and does not override user rights.
        </p>
      </Section>

      <Section n={5} heading="Who we share data with">
        <p class="policy-text">
          We share personal data only as needed to operate the Services:
        </p>
        <List
          items={[
            "Hosting and infrastructure providers",
            "Analytics providers",
            "AI providers (for AI summaries)",
            "Funders and partner organisations",
            "Legal/regulatory bodies",
          ]}
        />
        <p class="policy-text">
          We do not sell personal data. All third parties processing data on our
          behalf are bound by data processing agreements requiring
          GDPR-equivalent protections.
        </p>
      </Section>

      <Section n={6} heading="International data transfers">
        <p class="policy-text">
          Where personal data is transferred outside the UK/EEA, we rely on
          appropriate safeguards such as Standard Contractual Clauses or
          adequacy decisions.
        </p>
      </Section>

      <Section n={7} heading="Data retention">
        <p class="policy-text">
          We will only retain your data for as long as we need it to fulfil our
          purposes, including any relating to legal, accounting, or reporting
          requirements.
        </p>
      </Section>

      <Section n={8} heading="User rights (GDPR)">
        <p class="policy-text">Users have the right to:</p>
        <List
          items={[
            "Access the personal data we hold about them",
            "Correct inaccurate data",
            'Request deletion ("right to be forgotten"), subject to legal/contractual limits',
            "Restrict or object to certain processing",
            "Receive their data in a portable format",
            "Withdraw consent, where processing is based on consent",
            "Lodge a complaint with a supervisory authority (e.g. the ICO in the UK, or their local EU data protection authority)",
          ]}
        />
        <p class="policy-text">
          To exercise these rights, contact{" "}
          <a href={`mailto:${PRIVACY_EMAIL}`}>{PRIVACY_EMAIL}</a>.
        </p>
      </Section>

      <Section n={9} heading="Cookies and similar technologies">
        <p class="policy-text">
          We use cookies to operate the Services. Currently, we only use
          strictly necessary session cookies, which enable core functionality
          such as keeping you logged in during your visit. These cookies expire
          once you close your web browser and do not persist on your device.
        </p>
        <p class="policy-text">
          Our analytics are configured to be cookieless. We do not use
          persistent cookies, tracking cookies, or third-party advertising
          cookies.
        </p>
        <p class="policy-text">
          If this changes in the future, we will update this policy to reflect
          the cookies in use and, where required, seek your consent.
        </p>
      </Section>

      <Section n={10} heading="Security">
        <p class="policy-text">
          We apply appropriate technical and organisational measures (e.g.
          encryption in transit, access controls) to protect personal data. No
          system is completely secure; users should use strong, unique passwords
          for their accounts.
        </p>
      </Section>

      <Section n={11} heading="Children">
        <p class="policy-text">
          The Services are intended for professional use by technical advisors.
          They are not directed at children, and we do not knowingly collect
          data from anyone under 16.
        </p>
      </Section>

      <Section n={12} heading="Changes to this policy">
        <p class="policy-text">
          We may update this policy as the Services evolve. Material changes
          will be notified to users (e.g. by email or in-product notice) before
          they take effect.
        </p>
      </Section>

      <Section n={13} heading="Contact">
        <p class="policy-text">
          Questions about this policy or how personal data is handled:{" "}
          <a href={`mailto:${PRIVACY_EMAIL}`}>{PRIVACY_EMAIL}</a>
        </p>
      </Section>
    </div>
  );
}
