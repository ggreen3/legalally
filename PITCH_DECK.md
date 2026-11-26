# LegAlly pitch pack

**Thesis:** Kenya’s courts have gone digital. The work around them is still fragmented. LegAlly is the operating system for that work.

## Corrections applied before presentation

Claude’s research pass found several contradictions. These were fixed locally before generating the deck:

- Agent copy now says “fallback live; embedded OpenCode service deployment-ready”.
- Fee estimator now defaults to 16% VAT, with the test expectation updated to `4408000`.
- BriefCase “AI draft” and “Generate case brief” now require the same explicit AI-use consent as Studio and reset it after use.
- Public impact statistics were replaced with sourced Afrobarometer, Judiciary and LSK figures.
- Ruff and the full pytest suite pass after these changes.

Still do before going on stage:
- Rotate or isolate the published admin demo password, and confirm `SECRET_KEY` is set in Vercel.
- Have an advocate check hard-coded contract and tenancy citations; do not demo those topics.
- Say “citations appear in the local fallback” rather than implying structured citations on every streamed answer.

## Slide-by-slide deck

**Design system:** near-black background, white type, one teal accent, amber only for “planned”. One idea per slide, with sources in a small footer.

### 1. The Friday problem

**Headline:** “Dismissed on Friday. Where does she go on Monday?”

- Illustrative user: Achieng, a shop assistant in Kisumu
- Only 47% think they could afford to take a legal problem to court
- Only 37% know of local legal-aid services

**Visual:** A phone with her question, then the two percentages in large type. Footer: Afrobarometer, 11 June 2026.

**Speaker notes:** Say clearly that Achieng is illustrative. Pause after her question. Let the survey figures show that her problem is not unusual.

### 2. Problem and solution

**Headline:** “Kenya does not need another legal chatbot. It needs connected legal work.”

- The public needs a starting point
- Firms need controlled matters, deadlines and money
- LegAlly connects both on one platform

**Visual:** Scattered tiles snap into one teal spine labelled identity, tenant, audit.

**Speaker notes:** An answer is only the first step. After it come a person, a matter, a deadline and a filing. Our insight is that the value lies in the system around the answer.

### 3. Why now

**Headline:** “The courts went digital. The ecosystem now has to connect.”

- E-filing in all courts since March 2024; no court printing of pleadings from July 2024
- 169,349 cases older than one year remained in June 2025
- 18,335 practising certificates issued in 2025

**Visual:** A three-point timeline with one large number at each point. Footer: Judiciary, Afrobarometer, LSK Annual Report.

**Speaker notes:** The World Bank’s JUPITER assessment supports people-centred justice reform. It reports court and attorney fees at about 39% of claim value. LSK states that membership exceeds 23,000 advocates.

### 4. The operating system

**Headline:** “One operating system for law in Kenya.”

- Practise: BriefCase, Agent, Spaces
- Access: The Checkbar, Access guides
- Grow and govern: Talent, Academy, Innovation, Platform

**Visual:** A hub-and-spoke map with all modules lit and an amber note on Agent: “fallback live”.

**Speaker notes:** These are connected parts of one product. Do not read every module aloud. Point to the three groups and move to the demo.

### 5. Live demo

**Headline:** “From a question to controlled legal work.”

- Ask The Checkbar
- Create a court registry task on a matter
- Show the audit trail

**Visual:** Full-screen product with a three-step progress bar. Keep a recorded backup ready.

**Speaker notes:** Ask “Is my dismissal without notice fair?” Then switch to a prepared, fictitious firm matter and say that this is the advocate’s side of the platform. LegAlly prepares filing work; filing happens on the official eFiling and Cause List portals.

### 6. Technical depth

**Headline:** “Built for accountability, not just answers.”

- FastAPI on Vercel, persistent Neon Postgres, JWT and bcrypt
- Tenant-scoped data, rate limits, audit logs
- Streaming over the Pico WebSocket, with local fallback

**Visual:** A left-to-right flow: user, authentication, tenant boundary, workflow, audit record. A side branch goes to the official court portals.

**Speaker notes:** The tenant is derived from the signed-in user, not from the request body. Conflict screening, CDD checklists, deadlines and a trust ledger with an overdraw guard sit on that foundation. Isolation is enforced in the application layer, so do not describe it as database-level security.

### 7. Responsible AI

**Headline:** “AI assists. A person remains responsible.”

- Consent gate on AI Studio and Agent
- Disclaimers, stored outputs, human review record for template drafts
- Free models disabled by default in the Agent service (not yet deployed)

**Visual:** Four gates in sequence: consent, draft, verify, record. Show the real consent checkbox.

**Speaker notes:** Draft court practice directions would require advocates to verify AI-assisted work and disclose the tool used; they are not yet in force. Our direction matches the verification duty. Tool and model disclosure still needs to be added, because provider labels are currently hidden in Studio.

### 8. Proof

**Headline:** “This is running today.”

- Live product with persistent database and public health check
- 17 passing tests, ruff clean, CI on GitHub
- Working flows: Checkbar, BriefCase, Spaces, Agent fallback

**Visual:** Three real screenshots: health response, test run, product. Label the section “Product proof”, not “Market traction”.

**Speaker notes:** We are showing working software, not adoption numbers. Metrics and audit views require sign-in; the health endpoint is public. Any sample listings or records on screen are demo data.

### 9. Differentiation

**Headline:** “Others solve a step. LegAlly connects the journey.”

| Alternative | Its strength | LegAlly’s angle |
| --- | --- | --- |
| Practice software: Yawakili, EliteLaw, CrestDex | Firm operations | Adds public access, talent, learning, workspaces |
| Legal AI assistants | Answers and drafts | Places AI inside consent, matter and audit workflows |
| Official portals | Authoritative filing and listings | Prepares work and links out |

**Visual:** A journey line from question to filing to career, showing where each category sits.

**Speaker notes:** Be generous about incumbents: some offer M-Pesa, payroll and accounting depth that we do not show today. Our bet is the connection between parts of the legal ecosystem. That bet still has to be validated with firms.

### 10. Business model (planned, illustrative)

**Headline:** “Firms pay for control. The ecosystem adds revenue.”

- Firm subscriptions and enterprise compliance workflows
- Workspace marketplace fees and talent placement
- Academy and CPD programmes

**Visual:** A stacked diagram with subscriptions as the base. An amber “Planned, not current revenue” label.

**Speaker notes:** Firm subscriptions come first. Public guides stay open. Pricing will be set through pilots; placement fees and CPD offerings need regulatory and accreditation checks.

### 11. Roadmap and impact

**Headline:** “Prove, deepen, then expand.”

- 90 days: pilot with a few firms and a legal-aid partner; close consent, citation and privacy gaps
- 1 year: paid firm product, deployed Agent service, Kiswahili access journeys
- 3 years: trusted legal infrastructure across Kenya, then assess East Africa

**Visual:** Three horizons, all marked planned. Under them: time to next step, deadlines tracked, drafts verified.

**Speaker notes:** These are targets, not commitments from partners. We will judge impact by whether people reach a next step and whether firms control work better. We will publish numbers only once we have measured them.

### 12. Join

**Headline:** “From legal question to next step. Build it with us.”

- Pilot firms
- Legal-aid and training partners
- Early users

**Visual:** A large QR code will be placed on this slide, pointing to https://legalally-ivory.vercel.app/waitlist, with the URL printed below.

**Speaker notes:** Return to Achieng. Ask the room to scan. Stop talking and leave the code on screen.

## 30-second hook

Picture Achieng, a shop assistant in Kisumu. On Friday she is dismissed without notice. On Monday, where does she start? What will it cost, and who can help? In Kenya, only 47 percent think they could afford to take a legal problem to court. Only 37 percent know of legal-aid services in their community. LegAlly starts with her question.

## 60-second pitch

Achieng is dismissed on Friday. Where does she start on Monday? Only 47 percent of Kenyans think they could afford to take a legal problem to court.

LegAlly is one operating system for law in Kenya. The public gets legal information and access guides. Firms get matters, deadlines, conflict screening, due diligence and a trust ledger. Talent, learning and workspaces connect around them.

It is live, with a persistent database, tenant isolation, audit logs and 17 passing tests. AI Studio and Agent require consent, and legal work still needs human verification. We prepare court tasks and send users to the official portals.

The courts have gone digital. We are connecting the work around them. Scan to join us.

## 5-minute timed script

**0:00–0:30 | Slide 1**

Picture Achieng, a shop assistant in Kisumu. On Friday she is dismissed without notice. On Monday, where does she start? What will it cost, and who can help? In Kenya, only 47 percent think they could afford to take a legal problem to court. Only 37 percent know of local legal-aid services.

**0:30–0:50 | Slide 2**

A chatbot can give her an answer. But then comes a person, a matter, a deadline, a filing. Those steps are disconnected. LegAlly is one operating system for law in Kenya.

**0:50–1:20 | Slide 3**

Why now? E-filing reached all courts in 2024. Yet 169,349 cases older than a year remained in June 2025, even after the Judiciary cut that backlog substantially. And 18,335 practising certificates were issued last year. The courts have moved online. The work around them needs to connect.

**1:20–1:40 | Slide 4**

LegAlly has three layers. Access: The Checkbar and public guides. Practice: BriefCase, the Agent and Spaces. Growth and governance: Talent, Academy, Innovation and Platform.

**1:40–2:40 | Slide 5, live**

Here is Achieng’s question. (Submit. Let it stream.) This is general information, not legal advice, and it says so.

Now the advocate’s side. In this fictitious matter I create a registry task. LegAlly does not pretend to be the court. It prepares the work, then links to the Judiciary’s own portal. (Open the link.)

And here is the audit trail: what was done, and when.

**2:40–3:05 | Slide 6**

Underneath is FastAPI with persistent Postgres. Passwords are hashed, sessions use tokens, and each firm’s data is scoped from the signed-in user. Conflict screening, due diligence checklists, deadlines and a trust ledger that blocks overdrawing all run here. That matters, because advocates have real anti-money-laundering duties.

**3:05–3:30 | Slide 7**

In law, a confident wrong answer causes harm. So AI Studio and Agent ask for consent. Outputs carry warnings. Template drafts can be marked as reviewed by a named person. Our embedded agent service, which is ready to deploy but not live, disables free models by default. AI assists; people stay responsible.

**3:30–3:45 | Slide 8**

This is working software: live online, 17 passing tests, continuous integration, and open for you to inspect. We are not claiming adoption we have not earned.

**3:45–4:05 | Slide 9**

Kenya already has good practice-management tools, AI assistants and official court portals. We do not replace the courts. Our difference is connecting public access, firm work and professional growth in one place.

**4:05–4:25 | Slide 10**

Our planned model starts with firm subscriptions. Compliance workflows, workspace fees, talent placement and training can follow. Public access guides stay open. Pilots will tell us what firms will pay for.

**4:25–4:45 | Slide 11**

In 90 days: pilots and tighter safeguards. In one year: a paid firm product and Kiswahili journeys. In three: trusted legal infrastructure for Kenya, measured by people reaching a next step.

**4:45–5:00 | Slide 12**

Achieng does not need a directory or a chatbot. She needs a way forward. Scan the code and help us build it.

Rehearse with a timer. If the stream stalls for more than a few seconds, switch to the recording.

## Judge Q&A

### 1. How do you protect client data?

We have password hashing, token authentication, application-level tenant isolation, rate limits and audit logs. AI prompts go to a third-party service, Pico, so users are told not to enter protected data without authorisation. Before real client use we need to confirm processing location, retention and training terms, and put a processor agreement and lawful transfer basis in place. We do not claim Data Protection Act compliance yet.

The ODPC’s AI guidance note addresses offshore AI processors; confirm whether it is final.

### 2. What about hallucinations?

We cannot eliminate them. We use disclaimers, instructions against inventing authority, stored outputs and human review. Review is not yet enforced on every output, and streamed answers need stronger source checking. That is a first-90-days priority.

### 3. Are you regulatory compliant?

We support compliance work; we do not certify it. The LSK AML guidelines require due diligence, risk assessment, seven-year record keeping and suspicious-activity reporting within 48 hours. We offer checklists and records today, not a complete AML programme. Conflict screening checks names in the firm’s own records only.

### 4. Is this just rebranded OpenCode?

No. The live Agent uses a fallback through Pico. A separate OpenCode SDK service is built with restricted permissions but not deployed. We will not present OpenCode’s branding as ours or imply endorsement.

### 5. How will you make money?

Firm subscriptions first, then compliance workflows, marketplace fees, placement and training. All are planned. Any fee linked to legal work or referrals needs advice on professional conduct rules first.

### 6. Who competes with you? Is this too broad?

Yawakili, EliteLaw and CrestDex serve firm operations, and some go deeper than we do. Breadth is our biggest execution risk. We will lead with BriefCase and The Checkbar and expand the rest only where pilots show demand.

### 7. Why Kenya?

There is a documented access gap, nationwide e-filing and a large legal profession. The law, courts and professional duties are local, so the workflows must be too.

### 8. What is live and what is planned?

| Live | Planned or not yet deployed |
| --- | --- |
| The modules, with early-stage depth | Embedded OpenCode service |
| Agent through the fallback | Revenue and paid pilots |
| Links and tasks for court portals | Any direct court integration |
| Spaces listings and enquiries | Marketplace payments |

## Three moments to emphasise

1. Question to streamed answer. It makes the public problem concrete in seconds.
2. Matter to registry task to official portal. It shows Kenyan context and honest boundaries.
3. Audit trail, then 17 passing tests. It shows engineering discipline beyond a prototype screen.

Before going on stage: deploy, scan the QR code with a phone on mobile data, submit a test signup, run the demo once end to end, and record the backup.
