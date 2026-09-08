# Legal posture

*Last reviewed 2026-09-07. This is an engineering document explaining design choices, not legal advice. Verify the cases and their current status before relying on any of it.*

## Why this section exists

Building codes are an odd corner of copyright. Model codes such as the International Building Code (IBC) are written by a private organisation, the International Code Council (ICC), and then adopted into law by states and cities. Whether the adopted text is still ICC's property or has become "the law" that anyone may copy is contested, and the answer currently depends on which federal circuit you are in. codecite is built so that it is clean under every plausible outcome.

## What the courts have said

- **_Veeck v. Southern Building Code Congress International_, 293 F.3d 791 (5th Cir. 2002) (en banc).** Once a model code is enacted into law, the enacted text enters the public domain. The court reasoned from _Wheaton v. Peters_, 33 U.S. 591 (1834), that the law belongs to the people bound by it. This binds Texas, Louisiana, and Mississippi only.
- **_Georgia v. Public.Resource.Org_, 590 U.S. ___ (2020).** The Supreme Court held that works created by legislators in their official capacity, including annotations, are government edicts and not copyrightable. It did not directly decide the incorporated-by-reference question.
- **_ASTM v. UpCodes_ (3d Cir., decided 2026-04-07, No. 24-2965).** The Third Circuit affirmed the denial of a preliminary injunction against UpCodes' free, verbatim republication of standards incorporated into law, finding fair use likely. This is a preliminary-injunction ruling on likelihood, not a final merits decision, and it is one circuit.
- **Ohio is in the Sixth Circuit**, which has not ruled the same way as the Fifth. The circuits are split on standards incorporated by reference, which is why _ICC v. UpCodes_ proceeded and why the Pro Codes Act (H.R. 4072) exists: it would confirm that a standards developer keeps copyright in an incorporated code provided it offers a free read-only copy.

Two fair positions to state without picking a side: ICC argues that code development costs real money and access fees fund it; critics reply that charging people to read a law they must obey is the wrong way to fund it, and that view-only free access mostly protects the business model. Both can be true.

## What Ohio specifically publishes

Ohio's building code is Ohio Administrative Code Chapter 4101:1. Rule 4101:1-1-01 incorporates the 2021 IBC, Chapters 2 through 35 and Appendix H, by reference; 4101:1-34-01 incorporates the 2021 IEBC. Ohio's *amendments* are published as OAC rule text on `codes.ohio.gov`, which is a government edict and free. The *unamended IBC body text* is not on the state site; ICC publishes it. ICC's free premiumACCESS tier is view-only under its terms of use, and automating around those terms is a contract breach regardless of the copyright answer.

## The posture codecite takes

1. **The repository is code, not content.** Pipeline, schema, MCP server, tests, eval harness, and an original synthetic "Model Building Code, 2026 Edition" written for this project. The synthetic corpus uses IBC-style numbering because that is what the parser must handle, but its sentences and values are invented. It was reviewed by hand for phrasing that tracked real IBC sentences and rewritten where it did.
2. **The operator supplies the corpus.** Users index files they lawfully possess: a purchased PDF, a licensed export, a firm's own standards. The tool does no network fetching of code text by default.
3. **The only fetch helper targets state law.** `codecite fetch-oac` downloads OAC rule PDFs from `codes.ohio.gov`, respects `robots.txt`, rate-limits to one request per second, identifies itself, and never touches any ICC domain.
4. **Nothing leaves the machine** unless the operator deliberately selects a remote embedding provider, and then only chunk text goes to that provider under the operator's own account.
5. **No redistribution.** The database stores the operator's text locally. Source files are referenced by path and hash, never copied into the repository.
6. **The server does not generate answers.** It retrieves and cites. Whether an AI's reading of a code is correct is a question for the client model and the human, not for this server.

Under _Veeck_ the operator's indexing is fine because the text is public domain. Under the Pro Codes Act it is fine because the operator uses their own licensed copy and the tool redistributes nothing. Under either _UpCodes_ outcome it is fine for the same reason. The only thing that would change this posture is a licence term on the operator's own copy that forbids local indexing, which is the operator's contract to read.

## What this repository deliberately does not contain

- Any sentence from the IBC, IEBC, IRC, or any other ICC publication.
- Any scraped content from ICC premiumACCESS or any login-gated site.
- Any pre-built index of a real code.

## Sources

- _Veeck v. Southern Building Code Congress Int'l_, 293 F.3d 791 (5th Cir. 2002) (en banc).
- _Wheaton v. Peters_, 33 U.S. 591 (1834).
- _Georgia v. Public.Resource.Org_, 590 U.S. ___ (2020).
- _ASTM v. UpCodes_, No. 24-2965 (3d Cir. Apr. 7, 2026): https://law.justia.com/cases/federal/appellate-courts/ca3/24-2965/24-2965-2026-04-07.html
- EFF summary: https://www.eff.org/deeplinks/2026/04/another-court-rules-copyright-cant-stop-people-reading-and-speaking-law
- Law360 on the Pro Codes Act context: https://www.law360.com/articles/2469911/building-codes-ruling-may-inform-ai-copyright-arguments
- Construction Dive on _ICC v. UpCodes_: https://www.constructiondive.com/news/icc-v-upcodes-can-a-private-organization-copyright-the-law/558723/
- Ohio Administrative Code 4101:1: https://codes.ohio.gov/ohio-administrative-code/4101:1
- OAC 4101:1-1-01 (incorporation by reference): https://codes.ohio.gov/assets/laws/administrative-code/rules/4101/1/4101$1-1-01_eff_3_1_24.pdf
