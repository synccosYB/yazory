# Workspace consolidation

The permanent rule is one person record, one working screen, and shared action handlers. Lists and queues select records; they do not maintain alternative person editors.

| Current surface | Purpose | Status / next work |
| --- | --- | --- |
| `/supporter-directory` | Search, import, add people | Person case connection controls moved to the workspace |
| `/supporter-directory/<id>/edit` | Directory person workspace | Identity, full addresses, cases, relationships, institutions, communication actions, activity, tasks and requests |
| `/people/<id>` and `/people/<id>/edit` | Canonical person links | Redirect to workspace when a directory profile exists; retain fallback for roles without a profile |
| `/people/profile/<id>/addresses` | Old standalone address page | GET redirects to workspace address section; POST keeps existing address handler and returns there |
| `/supporters/<id>` | Case supporter history | Still needs consolidation of case-specific pledge, payments, children and status tools |
| Case supporter edit | Case-specific details | Still active; preserve relationship, pledge and permission editing until the workspace supports them |
| `/communications` | Inbox and communication queue | Shared delivery handlers reused in person workspace; inbox stays a queue |
| `/families/<id>/helpers/work` | Case work queue | Retained; action handlers already shared, UI consolidation remains |
| `/tasks` | Staff work queue | Retained; standalone task creation remains, call follow-up creation available on person workspace |
| `/people/matching` | Identity and relationship review | Retained; specialized evidence review |
| Case profile | Case workspace | Case page consolidation remains |

This release is the first person workflow pass, not removal of every duplicate page. No schema migration is required. Existing POST endpoints remain compatible. Case activity on the person workspace is restricted to accessible cases, and enforced fundraiser supporter assignment is respected.
