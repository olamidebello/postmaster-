# Postmaster Android
Signed development website client: com.justisolve.postmaster, version 1.0.0, Android 8+, target API 35. APK: app/assets/postmaster.apk. Checksum and public certificate fingerprint: release.json. Android device acceptance testing remains outstanding.

Supports HTTPS, JavaScript/DOM storage, user-selected PDF/image/CSV uploads, Home/Reload/Browser controls, back navigation and state restoration. External HTTPS sites including payment checkout open the browser. Browser downloads may require a separate sign-in. No TLS bypass, cleartext HTTP, native push, offline mail, biometric login, background worker, camera or microphone permission.

Install page: https://postmaster.justisolve.com/install. Internet and valid website HTTPS are required. The app does not embed login credentials or grant administrator access.

## Build
Set ANDROID_HOME to SDK platform 35/build-tools 35.0.0; install a JDK or set POSTMASTER_ECJ_JAR. Set POSTMASTER_KEYSTORE and POSTMASTER_KEY_PASSWORD, optionally POSTMASTER_KEY_ALIAS (default postmaster), then run `bash mobile/android/tools/build.sh`. Private signing material is preserved separately and excluded from public repositories. Reuse the keystore and increase versionCode for compatible updates.

## Deploy
Run ansible-pull with this repository's ansible/mobile.yml on Olamidepanel. Run ansible-pull with olamidebello/africanappsstore and ansible/deploy-postmaster-mobile.yml on the store host. These preserve existing service configuration and data. Publishing source alone does not update live websites.
