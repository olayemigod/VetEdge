# Veterinary Training Centre Manual QA Checklist

Use this checklist before handing the Veterinary Training Centre to clinic trainers or doctors.

This QA pass must not create, edit, submit, cancel, or delete clinical, billing, stock, accounting, lab, vaccination, Hospitalisation, grooming, boarding, notification, or other live business records.

## Access and Navigation

- [ ] Open Desk and confirm the Veterinary workspace/sidebar shows `Training Centre`.
- [ ] Click `Training Centre` and confirm the page opens at `/app/veterinary-training-centre`.
- [ ] Confirm the page title is `Veterinary Training Centre`.
- [ ] Confirm the page explains module-by-module learning in user-friendly wording.

## Role Visibility

- [ ] Sign in as a doctor role user, such as `VetEdge Doctor` or `Veterinary Doctor`, and confirm Doctor Operations modules are visible.
- [ ] Sign in as Branch Manager or Administrator and confirm available modules are visible.
- [ ] Sign in as a non-relevant role, where a safe test user exists, and confirm access is limited.
- [ ] If role behaviour differs from the expected result, verify roles in Role Permission Manager before changing documentation or code.

## Module List

- [ ] Confirm each module card shows a clear title.
- [ ] Confirm each module card shows a practical short description.
- [ ] Confirm each module card shows role group and status.
- [ ] Confirm `Read Guide` appears on every module card.
- [ ] Confirm `Watch Video` is disabled or clearly shows `Video coming soon` when no video URL exists.
- [ ] Use search to find modules by title, workflow wording, and role group.
- [ ] Confirm search results update without refreshing the page.

## Guide Reader

- [ ] Open every module from the list.
- [ ] Confirm `Read Guide` renders the Markdown guide.
- [ ] Confirm Mermaid workflow diagrams render as visual diagrams where present.
- [ ] Confirm invalid Mermaid diagrams leave the source visible with a friendly note instead of breaking the guide.
- [ ] Confirm headings, tables, checklists, code blocks, and links are readable.
- [ ] Confirm non-Mermaid code blocks still display as normal code blocks.
- [ ] Confirm the `Back to modules` button returns to the module list.
- [ ] Confirm no developer wording appears to doctors, such as `manifest`, `markdown path`, `module_id`, or `API error`.

## Practice Exercises

- [ ] Open the `Practice Exercise` tab for each module.
- [ ] Confirm modules with a practice exercise show the expected exercise from the guide.
- [ ] Confirm modules without a practice exercise show a friendly empty message.
- [ ] Confirm trainers can still find the exercise inside the full guide.

## Screenshots

- [ ] Open the `Screenshots` tab for each module.
- [ ] Confirm screenshot references appear where the guide contains screenshot placeholders.
- [ ] Confirm pending or missing screenshot files do not break the page.
- [ ] Confirm the guide explains that screenshots may be placeholders until captured.

## Video Readiness

- [ ] Confirm modules without a `youtube_url` show `Video coming soon`.
- [ ] Confirm no real YouTube video is embedded unless a safe YouTube URL is present in `training_modules.json`.
- [ ] If testing a temporary YouTube URL in a local-only branch, use only `youtube.com`, `youtu.be`, or `youtube-nocookie.com`, then remove it before release unless approved.
- [ ] Confirm invalid non-YouTube URLs are not embedded and show a review message.
- [ ] Confirm video titles in `training_modules.json` are useful for future recordings.
- [ ] Confirm every module has `video_status` set to `Not Recorded` unless a real approved video exists.

## Browser and Layout

- [ ] Confirm the browser console has no new Training Centre errors.
- [ ] Confirm the page is usable on a normal Desk screen.
- [ ] Narrow the browser window and confirm cards, tabs, and guide content remain readable.
- [ ] Confirm long tables and code blocks scroll instead of breaking the layout.
- [ ] Confirm image placeholders do not overlap text.

## Data Safety

- [ ] Confirm no patient, Pet Owner, appointment, consultation, invoice, payment, lab, vaccination, Hospitalisation, grooming, boarding, stock, or notification records were created or modified during QA.
- [ ] Confirm no role permissions were changed.
- [ ] Confirm no submitted invoices were altered.
- [ ] Confirm Markdown files remain the source of truth for guide content.

## Sign-Off

- [ ] Training Centre opens from the Veterinary workspace/sidebar.
- [ ] Doctor Operations modules are visible to the intended roles.
- [ ] All modules open and render.
- [ ] Video placeholders are clear.
- [ ] Screenshot placeholders are safe.
- [ ] No business records were changed.
- [ ] Issues found during QA are documented for follow-up.
