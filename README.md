# siglia — Siglia, Inc.'s public Claude marketplace

One plugin, **siglia-domain**: domain knowledge for financial research on US public companies.
- **Skills:**
  - `siglia-fin-concepts`: financial-concept rules, each with its primary source;
  - `siglia-xbrl-element`: US GAAP XBRL elements;
  - `siglia-def-check`: re-reading a definition at its source.
- **Five specialist agents:** SEC disclosure, credit and bank, SaaS metrics, data platform, AI product evaluation.

Install in Claude (app or Claude Code): add the marketplace `Siglia-io/siglia-skills`, then install **siglia-domain** and turn on auto-update.
In Claude Code, run `/plugin marketplace add Siglia-io/siglia-skills`, then `/plugin install siglia-domain@siglia`.

The plugin is published automatically whenever these skills change. The repository carries public, domain-knowledge content only.
All rights reserved.
