<!-- insertion marker -->
<a name="1.1.0"></a>

## [1.1.0](https://github.com/kschweiger/verve-backend/compare/1.0.0...1.1.0) (2025-12-29)

### Features

- 📊 expose speed calculation in track data API ([1180c18](https://github.com/kschweiger/verve-backend/commit/1180c188358f49c067eb479b7d4c97f1fea43fdd))

### Bug Fixes

- **statistics:** Fix issues with optional distance in year and week endpoints ([85d90df](https://github.com/kschweiger/verve-backend/commit/85d90df233c3f16dedf6d49c68113d314653c803))

<a name="1.0.0"></a>

## [1.0.0](https://github.com/kschweiger/verve-backend/compare/4e2c077fa2a0a57f1fcd5587757013e4a22e5589...1.0.0) (2025-12-26)

### Features

- 🗄️ add alembic migrations (#26) ([497112f](https://github.com/kschweiger/verve-backend/commit/497112f612ae7e32eef1581b5bb3f39059242229))
- 📏 Make distance optional for non-distance-based activities (#8) ([5293716](https://github.com/kschweiger/verve-backend/commit/5293716cd7412f790c8ff8db3fba86616b3cb779))
- 🌍 Add location-based goals and activity tracking with geospatial queries (#24) ([29ab419](https://github.com/kschweiger/verve-backend/commit/29ab419c7336dfc4a9dd60a7690c40413dc0b81f))
- **activity:** implement delete route for activities (#18) ([e1784cb](https://github.com/kschweiger/verve-backend/commit/e1784cb901fe3079ea47f772ada13718a041573b))
- ♻️ extract and expand media management routes 📸 ([3149654](https://github.com/kschweiger/verve-backend/commit/3149654130f3447dd014ac2cff8bd66f796ac9a0))
- add route to get all equipment sets of a user ([7a9477d](https://github.com/kschweiger/verve-backend/commit/7a9477dbe1b9d3a4395580c22ba7d561d2acfb9c))
- ✨ add support for weekly goals with ISO week numbering ([53c047c](https://github.com/kschweiger/verve-backend/commit/53c047c864f2785acb7b4baf1c06682e1c649a03))
- **setup_db:** Generate admin user when setting up database ([e4d540e](https://github.com/kschweiger/verve-backend/commit/e4d540e2166b274b3336b36ff0c7e4a26150c6ee))
- 🎯 Improve goals (#15) ([348049c](https://github.com/kschweiger/verve-backend/commit/348049c27134a69154354a26031244aa850cfb84))
- ✨ implement equipment set management and default equipment assignment (#13) ([4fd644c](https://github.com/kschweiger/verve-backend/commit/4fd644c87ad2c4d6c569bfa3386f399965b48e26))
- Implement route for aggregating activities in a month (#10) ([d072bb2](https://github.com/kschweiger/verve-backend/commit/d072bb28192d8415e932a82692f404fa4d2b74ef))
- Add rust style Result object to enable error propagation from crud methods to routes ([3adb9f2](https://github.com/kschweiger/verve-backend/commit/3adb9f29ba7543f24e79f6289adb34a108e71457))
- Add swimming activity type and automatic metadata validation with target-based model discovery (#9) ([017893b](https://github.com/kschweiger/verve-backend/commit/017893b0d3938f56f21bf3c862bc7b5c128b2416))
- **highlights:** Add route that returns all possible highlight metics ([b68decf](https://github.com/kschweiger/verve-backend/commit/b68decf9013d13a517cbaedf20ba6bac3802870f))
- ✨ Add Celery task processing & activity highlights system (#6) ([cfde41f](https://github.com/kschweiger/verve-backend/commit/cfde41f155d548c4831d3b101d18026cb36e8e74))
- ✨ Add equipment management and standardize API responses 🔧 ([6130939](https://github.com/kschweiger/verve-backend/commit/6130939e2a6fb80b3054c119c5cbf403c9444410))
- ⚙️ Add equipment management with activity associations ([9f3a623](https://github.com/kschweiger/verve-backend/commit/9f3a6233290ee59a448313ce8f318cb053856368))
- 🔐 add password change endpoint with validation ([19237a5](https://github.com/kschweiger/verve-backend/commit/19237a59c3974c6ab1d23addcf8dca91cc5fe7b9))
- ✨ add user settings management and activity type defaults 🎯 ([cf63812](https://github.com/kschweiger/verve-backend/commit/cf63812c0cb687fbd031ae67994f023cbf0c612c))
- Implement per-day week statistics ([1dafe12](https://github.com/kschweiger/verve-backend/commit/1dafe129de833dd0d0e973a2a5898903ea4ce8c7))
- Add route to update some activity values ([adc3ab2](https://github.com/kschweiger/verve-backend/commit/adc3ab273c655dd1576f0d70d9f85610ce7bded2))
- Implement year statistics endpoint with activity aggregations 📊 ([caf0906](https://github.com/kschweiger/verve-backend/commit/caf09062717f20d323b8e3dee712052cc3e4d34e))
- add 🌍 localized activity names with automatic generation ([e7e631f](https://github.com/kschweiger/verve-backend/commit/e7e631f5f1586362f166b3f4ba32e804d473a739))
- Add route to retrieve track data for a given activity ([e6b3f4a](https://github.com/kschweiger/verve-backend/commit/e6b3f4a925579e6e8a8fd9578ff8eb8a336e49a1))
- **get_activities:** Add pagination, year/month and type filter (#1) ([e60dbfa](https://github.com/kschweiger/verve-backend/commit/e60dbfa99915ae82db76ee99e8c693e59699f309))
- Add router collection endpoints used to resolve data. First endpoints resolves all activity types and sub_types ([8a5296f](https://github.com/kschweiger/verve-backend/commit/8a5296f36b0ffa61e800d21514c29132a155a5a5))
- Add CORSMiddleware for frontend ([d8c53fa](https://github.com/kschweiger/verve-backend/commit/d8c53fa7505c300ee85ed5eeb2e0dedb0f4fdc03))
- Added route that creates activity based on track ([3fae78d](https://github.com/kschweiger/verve-backend/commit/3fae78d72c8d5b7ea1b8ca6cf1bf0d413946fbbd))
- Add user settings table ([c4fe58f](https://github.com/kschweiger/verve-backend/commit/c4fe58f0b6c446747d111cb95ada3ffa126bcac5))
- Add route to upload images for activities; Define route Tags with enum ([1408de8](https://github.com/kschweiger/verve-backend/commit/1408de823d4604ae2659207b7ab8270f0260bac3))
- Add integration with boto3 compatible object store; Raw track data is save to object store ([34ff27d](https://github.com/kschweiger/verve-backend/commit/34ff27df1527d7a28a9ea0567c83cf69f8a0245b))
- Added postgis based track points to model; Added route to insert gpx and fit files; Added heatmap ([a1567c8](https://github.com/kschweiger/verve-backend/commit/a1567c8d5ad163c4414855d902d7174ba7caed4a))
- Add activities and RLS implementation for user data management ([08fd224](https://github.com/kschweiger/verve-backend/commit/08fd224fea3036f3f0b8af590164a441f2f51345))

### Bug Fixes

- **crud:** avg/max velocity, power, and heartrate are set correctly in update_activity_with_track_data (#25) ([af5e81f](https://github.com/kschweiger/verve-backend/commit/af5e81f0fa8c7577f14bb71f5327e5f8c112214c))
- **meta_data:** fix typo in LapData ([2dff06f](https://github.com/kschweiger/verve-backend/commit/2dff06f3511729ffd278a4a68f1475f33673f531))
- **goal:** Add week filter to get goals ([c02fd0b](https://github.com/kschweiger/verve-backend/commit/c02fd0b7a64a9d7fed9cbe98b596ca40f225eac2))
- **statistics:** Increase max_length to 6 for CalendarResponse ([56536b5](https://github.com/kschweiger/verve-backend/commit/56536b505ba28740f00e1ce407495e45321621d3))
- Set bucket name based on configuration ([dfcfa02](https://github.com/kschweiger/verve-backend/commit/dfcfa028cac0b49ee71ac499b8d83d4f2fdef0d2))
- **create_auto_activity:** Add name to response ([47586f9](https://github.com/kschweiger/verve-backend/commit/47586f9ef9057a2a82f7ef3356a42a3fa8c80f66))
- **get_activities:** Add order to returned activities ([8089adc](https://github.com/kschweiger/verve-backend/commit/8089adc8bb579c6056ba5535d98bef8b8e0f7d42))

### Code Refactoring

- **logging:** rework logging setupa (#23) ([80c1476](https://github.com/kschweiger/verve-backend/commit/80c1476841b0d87ab0ca5383460c6a466ba2ce7e))
- 🔄 extract object store deletion logic into reusable utility ([fa8ee05](https://github.com/kschweiger/verve-backend/commit/fa8ee05fdf6aa4e4e99c6e35c4bfaf266559c55c))
- Route for creating activity now uses method in curd module ([eb77cfa](https://github.com/kschweiger/verve-backend/commit/eb77cfad6b0e15a94d06b7a97143a6f8a3bda64c))
- **meta_data:** Use enum for swim styles ([c065c20](https://github.com/kschweiger/verve-backend/commit/c065c20794a1b940d9ae626c7e55063bbc9fb688))
- **EquipmentType:** Add Hometrainer type ([2a69e76](https://github.com/kschweiger/verve-backend/commit/2a69e760d8e7865642e46891c20a71136931de5f))
- **get_weekly_stats:** Add information about subtype and add raw pie chart data per sub_type ([04e3840](https://github.com/kschweiger/verve-backend/commit/04e384067592e11d52a5cc75b1a67860ec54cef6))
- Move activity name to main Activity object ([153e71f](https://github.com/kschweiger/verve-backend/commit/153e71f9f14e75085f158588ab903cd96d40444b))
- **heatmap:** Move query to resource ([ccd4950](https://github.com/kschweiger/verve-backend/commit/ccd49504bab775e90c77ce045382eaaa3f08037e))
- **heatmap:** Move heatmap endpoint to different path and router ([ebda8c2](https://github.com/kschweiger/verve-backend/commit/ebda8c2f01a3d053be7b9d42f977107a07e6e8a5))
- Add max metrics to activity ([5d37a48](https://github.com/kschweiger/verve-backend/commit/5d37a48fd8843a1928aa41ed3cb3082722761444))
- Setup testing and minor refactorings ([3b6df2a](https://github.com/kschweiger/verve-backend/commit/3b6df2a2e43c2f9fcc0f660718d11ea28e234504))
- ActivityType can be set in auto activity creation route ([d9c5988](https://github.com/kschweiger/verve-backend/commit/d9c5988ecb1c51d1d5a4ce3291398869c2f8a239))

