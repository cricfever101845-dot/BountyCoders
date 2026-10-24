# Portable BountyCoders submission

The master source repository is `D:\SCAR_IDE\BountyCoders`. The local application and ZIP live in `dist\BountyCoders_Submission_Windows_x64` and `dist\BountyCoders_Submission_Windows_x64.zip`. Generated files are ignored by Git.

From the repository root, build on a Windows x64 development PC with Python and pip:

```powershell
.\tools\portable_builder\BUILD_PORTABLE_WINDOWS.bat
```

The build refuses to overwrite an existing release folder. Preserve or rename it before a fresh build. Downloads default to `%LOCALAPPDATA%\BountyCodersBuilds\download_cache`. This machine's existing Python, Java, Flask wheels, fonts, and TinyCC archives have been reused there. Use `--cache <folder>` to select another cache. Download checksums and dependency versions are recorded in this directory. A changed upstream archive fails checksum verification instead of silently changing the release; Java's download endpoint is upstream's current JDK 21 endpoint, so retain the verified cache for identical rebuilds.

The builder copies source/assets, creates a clean demo database, bundles embedded Python 3.13, Temurin JDK 21, TinyCC 0.9.27, Flask dependencies, and local fonts. It verifies the release before creating and integrity-testing the ZIP. Only an extracted release is runnable on the college PC; no language tools need installation.

A fresh Git clone can build from `question_bank.json` without a personal database. To develop locally, install `requirements.txt`, then create a NEW database explicitly:

```powershell
python tools\portable_builder\create_demo_database.py
```

This command refuses to overwrite an existing DB. Personal DB files are ignored and retained on this machine. The staged Git deletion removes the previously tracked DB from the next commit; old Git history may still contain historical database data.

To verify the existing release:

```powershell
.\dist\BountyCoders_Submission_Windows_x64\runtime\python\python.exe -B .\dist\BountyCoders_Submission_Windows_x64\verify_release.py
```

Verification uses temporary accounts and a temporary database, tests Python/Java/C success, wrong output, compilation errors, runtime errors, and bounded infinite loops; checks HTML structure and all 45 HTML answer variants; exercises real Flask HTTP signup/login/pages/static assets and all 60 course progression steps with duplicate-answer rejection and bounty totals. It removes development language-tool paths during the checks. A successful run writes `VERIFICATION_REPORT.json` in the release. Test-generated answers exercise execution/grading contracts; they do not prove the pedagogical algorithms in every exercise. HTML/CSS validation checks structure rather than browser pixels or CSS rendering.

Diagnosis: Zig 0.13 reproduced a bounded 25-second timeout compiling a minimal stdio program. The previous timeout left a Zig process behind. Compiler subprocess pipe inheritance made cleanup unreliable; output now uses temporary files, with bounded waits and Windows process-tree termination. TinyCC compiled and ran that same program immediately and passed the language and progression checks. Zig is excluded from the final release; unused old files remain preserved outside it. TinyCC's matching source archive and LGPL license are included under `licenses\tinycc`.

Limitations: Windows 10/11 x64 only, writable extracted folder, modern browser with JavaScript/video support. Submitted programs run with the logged-in Windows user's permissions. This is a trusted local college demo, without a security sandbox. No clean physical college PC has been available for a separate-machine test.
