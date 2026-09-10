<!-- Baseline taken 2026-09-10, before any migration.

     CONDITIONS THIS WAS TAKEN UNDER — both matter when reading it:

     1. The vault working tree was DIRTY (43 changed files across alz-olf,
        astro_atp, intellicage, oldenlabs, lit/ and logs/library-status.md),
        so this describes the working tree, not a commit. It is indicative,
        not reproducible from a tag.
     2. It is SHALLOW BY CONSTRUCTION. No project has a project.json yet, and
        a config that will not load short-circuits every other check for that
        project. So the shape, drift, data-root and provenance checks have not
        run against anything. Expect the real finding count to rise sharply
        once Plan 2 writes the eight config files.

     Produced by calling check_vault.collect()/render() directly rather than
     main(), so that nothing was written into the vault.
-->

# Vault status

Generated 2026-09-10 by `check_vault.py`. This file is GENERATED — do not hand-edit.

**8 findings** — 0 AUTO, 8 REPORT.

`AUTO` is mechanically repairable. `REPORT` needs a human and is never repaired automatically.

## alz-olf

- `REPORT` **no-project-config** — no project.json in /mnt/sysfs01/users/cagatay/code/neubrain/projects/alz-olf

## aon-pir-rev

- `REPORT` **no-project-config** — no project.json in /mnt/sysfs01/users/cagatay/code/neubrain/projects/aon-pir-rev

## astro_atp

- `REPORT` **no-project-config** — no project.json in /mnt/sysfs01/users/cagatay/code/neubrain/projects/astro_atp

## compare-svm

- `REPORT` **no-project-config** — no project.json in /mnt/sysfs01/users/cagatay/code/neubrain/projects/compare-svm

## intellicage

- `REPORT` **no-project-config** — no project.json in /mnt/sysfs01/users/cagatay/code/neubrain/projects/intellicage

## oldenlabs

- `REPORT` **no-project-config** — no project.json in /mnt/sysfs01/users/cagatay/code/neubrain/projects/oldenlabs

## theta-pac

- `REPORT` **no-project-config** — no project.json in /mnt/sysfs01/users/cagatay/code/neubrain/projects/theta-pac

## writing

- `REPORT` **no-project-config** — no project.json in /mnt/sysfs01/users/cagatay/code/neubrain/projects/writing
