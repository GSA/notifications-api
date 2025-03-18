## Reflections after sunset decision

Q: How did we decide what to work on / get to notifications? 

-   We started with understanding of the market needs.

    - Idea of Public Benefits Studio spun out of 18F Public Benefits Portfolio. The team had a deep understanding of past challenges of implementing tech in government.

    - Team also had a lot of understanding of the unique constraints of working in the benefits space which is at the state and local level (vs. feds) 

-   We knew our users really well, including their constraints and goals.

    - Constraints of building tech for other people/jurisdictions:

        - Integration deters adoption

        - Procurement timelines / spending ANY money takes time (free is fast)

        - Program teams have needs they cannot articulate to their technology stakeholders  (we gave them an easy solution to sell)

        - Program teams expressed problems with communicating to the public and we found in-flight projects that met these needs.

-   Matched technology with potential impacts, illustrated how text messages can help applicants/beneficiaries and improve the relationship between gov't and the public

Q: How did we define success, or how did we decide what success was?

-   Identified the constraints and barriers we hoped to reduce or overcome (time to launch, procurement/security hurdles, technical expertise, etc.), established what would indicate that we were having an impact, and then tracking it.

-   Partners over and over again shared quotes with the idea of "This is just what we were looking for!"

-   Wanted to build a product that was easy to get started with and had low-stakes for real-world experimentation.

-   "Good enough" metrics

    -   We wanted an impact on recipients and programs, and we got this in some cases (although not as many as we hoped). We did a good job at tracking partners (increasing), usage (increasing), time from onboarding to sending (decreasing). 

Q: How did we set ourselves for success? What factors contributed to it? 

-   We prioritized partnerships via a free pilot opportunity. We worked deeply with our first 4 pilot partners to understand their use cases and needs before scaling back "ad hoc" support

-   Leveraged existing resources

    -   We leveraged American Rescue Plan money and the TTS BPA to get a full development team onboard quickly.

    -   Leveraging Customer Experience/Life Exeriences and Office of Evaluation Sciences priorities and people

    -   We had a full team (product, UX, content, front-end and back-end engineering) from the beginning

    -   We did what we could given federal hiring constraints, but at various times that did pose serious challenges for the team

-   We narrowed in on common use cases in the benefits space and had good story telling for potential customers about HOW texting could have an impact on program ops. 

    -   We stayed flexible and open to a wide range of use-cases, so we could follow demand  

-   We got program teams excited enough to advocate this tech opportunity to other stakeholders

-   Able to springboard ATO because we just had to document the system vs build it from scratch

    -   Fortunate that we had someone experienced who lent a hand with the original LATO

-   For a long time we had leadership alignment and legal alignment - this will be critical for anyone trying to do a similar thing in the future

    -   Approved for beta:

    -   TTS approved beta status 

        -   We proved out demand

        -   We proved that the product was stable and is being used for what it says it can do, reliably,

        -   We achieved full ATO

-   Continually sought to templatize and simplify partnerships and onboarding processes with self-service guides, videos, etc.

-   We built an opt-in pipeline for potential customers, we had a clear intake process and screening questions which we tied back to other metrics we wanted to track

Q: As we sunset, What signs of success are we still seeing?

-   Even as we were discussing sunset, we were getting partner intake forms submitted

-   Partners are seeking to continue using the service, in any way they can

-   Number of partners signed, and number of partners sending messages, were increasing

-   Federal partners wanted to pay

-   The public knows about our product, we come up in google searches for "text messages for government"

-   Programs we shared best practices and learnings with continue to say they've appreciated and use these

Q: Where have we left off?

-   Partners were scaling use within their agencies:

    -   Had a few partners moving from 1-2 texting campaigns / teams using it to adding more teams and use cases

-   We had a pipeline of at least 4 more partners ready to sign an MOU before we had to stop

    -   7 potential partners reached out ready to use the platform before we had to stop

-   Two programs saying "take my money" 

-   A finished, but not approved, pricing model. The thorny part remaining was figuring out what costs could be reimbursable vs appropriated and how that could change in future years.

-   Marketing and comms ready to promote updated service model (paid/free)

-   We have best practices related to texting to share but are not public yet on the site (these are useful beyond notify)

-   If we could have kept positions stable (terms) / filled, we think had enough staff to scale significantly

Q: What advice do we have for future us? Were there any missed opportunities?

-   Many programs are texting about the same things (application deadlines, reminders etc). We had hopes to prepopulate tested-plain language templates on to Notify to help standardize comms across agencies

    -   Also hoped to have templates translated and vetted by non-English speakers in common languages

-   TCPA-related liability concerns mean commercial providers require government agencies to go beyond what is legally required (eg. get explicit consent), which means that for some use cases they can't text at all. Clarified or more forceful guidance from the FCC or a new process for gov agencies could alleviate this. See below. 

-   Agencies have continued to have trust/ spam issues and we had hoped to develop a trusted gov't short-code (similar to 411). Only an internal fed team has leverage like this at scale.

-   Features to support existing users

    -   Release a public API (this was next up for a) the large use cases and b) to allow us to remove some problematic reporting functionality in the UI)

    -   Better scheduling features, set it and forget 

    -   Some way to save or reference an existing list of recipients

-   Helping new texting programs get off the ground faster in a more informed way -

    -   Learning collaborative - users can learn directly from each other - it's not just Notify but sending good text messages and learning from other agencies that have real evidence and experience sending messages

    -   Enabling resource sharing

Q: If a single agency wanted to start a texting program, what would we recommend they consider for metrics of success?

-   Is this delivering on your mission? 

-   What is the change you are hoping to see? 

    -   Better customer service can be enough

    -   Serve more people, save money/churn, etc

-   Are sending text messages saving staff time?

    -   Fewer missed deadlines, less follow-ups needed etc. 

Q: Did forking a thing increase leadership's willingness to do it? 

-   It helped build confidence knowing that other countries had successfully implemented it. We were able to pull metrics and reference elements such as costs and timelines. The idea of not reinventing the wheel was crucial. The U.S. is behind in this regard, but the process itself isn't technically that complicated.

-   The completeness of the codebase was not critical. 

-   Notify has a core function which is easier to understand and sell. 

Q: About products centrally provided by government

-   GSA has incentives and requirements, such as privacy protection standards, that the private sector may not have. 

-   Should one government entity rely on another as a provider? It matters where data resides, and the risks associated with this have evolved over time.

-   Our opinion has shifted over time: we think there is a much narrower list of shared services the federal government should offer than we did when we started. 

-   There is a power dynamic when the federal government does anything, this cannot be replicated outside the gov, and this can have both positive and negative effects.

-   On a basic level, there is value in shared services, but only if there's someone responsible for running them.

-   It is important to note that some states do not - and have never - trusted the federal government on matters of data privacy.

-   Financial expectations from the private sector don't fit well in this environment. 

    -   Appropriated funding and timelines align very poorly with scaling/ volume based services 

    -   No guarantees on runway

    -   "Fully reimbursable" to the exact dollar is not a thing in private sector; in particular it was difficult to establish techniques to charge partners and cover shared service costs without risking a surplus (even the possibility was not allowed). 

-   The need for products is, in part, because of auxiliary challenges (procurement, private-sector cooperation, etc). 

    -   Should we wait till these problems are solved before doing anything? Not necessarily. But that doesn't mean the federal government is the best place to do it.

-   The federal government is well positioned establish common standards that people could use (ex. USWDS). Doesn't have to be a shared service itself.

Q: Did forking Notify from the UK make a difference in building leadership support?

-   It made a significant difference that other countries had already implemented it, allowing us to pull useful metrics. The team structure, customer focus, and story were especially important.

-   We could have forked the libraries and told the same story, but the story itself was more important than the code base.

-   The case was clear: the government should communicate by text. 

-   Notify is conceptually easy to understand, both what it is and why it would be important. 

Q: Would we fork wholesale again? 

-   Yes, but maybe not all of it.

-   The size and scope of the codebase made the founding team feel that a relatively large team was necessary up front. 

-   At the time of sunset, the team was only starting to truly deal with conceptual mismatches and architectural issues. Or rather it had been working on them for a while, but signs were they still had a long way yet to go.

-   The original codebase wasn't designed to be forked. 

    -   Architectural decisions made components tightly coupled and therefore harder to change for our specific instance

    -   We're not sure

Q: Do we tell people not to fork ours? 

-   There are layers of our changes on top of a library of old debt. 

-   We've stripped out several pieces to focus on texting. 

-   Lots of "whack-a-mole" in the current deployment in the code. 

-   We didn't have high code quality in the received product and our team didn't fix all of that. 

-   We had not validated the API for public consumption (but believe it would have been OK). 

Q: What were some strong aspects of Notify.gov?

-   Research informed decisions made the project stronger. 

-   Our best practices worked well and were appreciated. 

-   Template management and user management were fine but incomplete. 

-   We solved some thorny architectural things re: scale and time zone.  

-   We would recommend thinking carefully before using it out of the box

    -   Note: Notify is written to use Cloud.gov, which not everyone has access to).  

    -   Not a blocker, but it would take some work to stand up. This could be replaced by going with a different cloud provider.  

    -   Be aware that the original application was not that well-architected for our use case, and we hadn't gotten all the way to aligning it with our use cases and personas. You're getting a bit of a chimera. 

Q: What are some lessons learned?

-   There is a need to have leadership alignment/advocates 

    -   Ex. managing budget cycles 

    -   We had ARP money and had stakeholders that understood the time it takes to get to financial sustainability

-   The products goals were misaligned with a risk-averse outreach approach. It was always a challenge to even tell people we exist, given the inherent possibility we might learn something that would make us choose to shut down the program. This made ithard to build awareness and trust. 

-   Solutions need to be adaptable to the agency that is actually deploying them.

    -   Ex. Notify started with no integrations 

    -   It was designed to be part of a larger workflow, to drop into a variety of situations. 

    -   It was intentionally kept small. There was no attempt for it to have the functionality of a CRM/management of workflows or store data.
