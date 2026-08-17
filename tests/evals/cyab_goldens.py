"""
Static golden Q&A pairs for the CYAB study "DE AI Assistant" use case,
sourced from Golden_Test_Table_Template.xlsx. No underlying source data
(endpoint tables, actigraphy records, etc.) exists for this use case, so
these goldens carry no retrieval context — only question + expected answer.

Q5 and Q6's expected answers include a plot as part of the golden answer.
Since there is no way to score a generated image against these, their
expected_output is a written description of what the reference plot shows
in place of the image itself.
"""

CYAB_GOLDENS = [
    {
        "patient_id": "Q1",
        "context": "",
        "input": (
            "What are the digital endpoints generated for CYAB study? "
            "Can you provide a description for the variables?"
        ),
        "expected_output": (
            "Daily endpoints:\n\n"
            "Endpoint | Unit | Description\n"
            "--- | --- | ---\n"
            "biobank_L5 | mg | The rolling average of UKBB ENMO over least active 5 hour window\n"
            "biobank_M10 | mg | The maximum rolling average of UKBB ENMO over 10 hour window\n"
            "biobank_enmocutoff_mvpa_mins | mins | Total minutes in moderate and vigorous physical "
            "activity based on UKBB's ENMO where ENMO is greater than 100\n"
            "biobank_enmocutoff_light_mins | mins | Total minutes in light physical activity based on "
            "UKBB's ENMO where ENMO is between 40 and 100\n"
            "biobank_enmocutoff_moderate_mins | mins | Total minutes in moderate physical activity "
            "based on UKBB's ENMO where ENMO is between 100 and 400\n"
            "biobank_enmocutoff_vigorous_mins | mins | Total minutes in vigorous physical activity "
            "based on UKBB's ENMO where ENMO is greater than 400\n"
            "biobank_enmocutoff_sedentary_mins | mins | Total minutes in sedentary physical activity "
            "based on UKBB's ENMO where ENMO is less than 10\n"
            "biobank_movement_intensity_average | mg | Average UKBB ENMO\n"
            "biobank_model_mvpa_mins | mins | Total minutes spent in moderate to vigorous activity "
            "based on UKBB's pretrained activity classification model\n"
            "biobank_model_sedentary_mins | mins | Total minutes spent in sedentary based on UKBB's "
            "pretrained activity classification model\n"
            "biobank_model_light_mins | mins | Total minutes spent in light activity based on UKBB's "
            "pretrained activity classification model\n"
            "biobank_wearing_detection_mins | mins | Total minutes of coverage based on UKBB's "
            "imputed value\n"
            "biobank_sleep_mins | mins | Total minutes spent in sleep based on UKBB's pretrained "
            "activity classification model\n"
            "ggir_L5 | mg | The least active 5-hour period within a 24-hour day\n"
            "ggir_M10 | mg | The most active 10-hour period within a 24-hour day\n"
            "ggir_acceleration_average_daily | mg | The daily average acceleration\n"
            "ggir_MVPA_in_mins | mins | Total minutes in moderate and vigorous physical activity "
            "based on GGIR's average daily acceleration where acc_day_mg is greater than 100\n"
            "ggir_light_activity_in_mins | mins | Total minutes in light physical activity based on "
            "GGIR's average daily acceleration where acc_day_mg is between 40 and 100\n"
            "ggir_moderate_activity_in_mins | mins | Total minutes in moderate physical activity "
            "based on GGIR's average daily acceleration where acc_day_mg is between 100 and 400\n"
            "ggir_vigorous_activity_in_mins | mins | Total minutes in vigorous physical activity "
            "based on GGIR's average daily acceleration where acc_day_mg is greater than 400\n"
            "ggir_sleep_duration_hours | hours | Total duration of sleep during the sleep window\n"
            "ggir_number_of_awakenings | awakenings | Total number of awakenings in the sleep window\n"
            "ggir_sleep_efficiency | % | Proportion of the sleep window spent asleep\n"
            "ggir_sleep_window_duration_hours | hours | Total duration of the sleep window\n"
            "ggir_sleep_window_end_timestamp | timestamp | Timestamp when sleep window ends\n"
            "ggir_sleep_window_start_timestamp | timestamp | Timestamp when sleep window begins\n"
            "ggir_waso_hours | hours | Total time awake after initially falling asleep\n"
            "ggir_wearing_detection_mins | mins | Total minutes of wearing based on GGIR's long epoch "
            "file where nonwearscore <=1 and clippingscore=0\n"
            "emd_step_count | steps | Total steps based on the empirical mode decomposition technique\n"
            "\n"
            "Hourly endpoints:\n\n"
            "Endpoint | Unit | Description\n"
            "--- | --- | ---\n"
            "biobank_MET | MET | The average Metabolic Equivalent of Task (MET) value\n"
            "biobank_movement_intensity_average | mg | The average Euclidean Norm Minus One (ENMO) "
            "value\n"
            "biobank_model_mvpa_mins | mins | Total minutes spent in moderate to vigorous activity "
            "based on UKBB's pretrained activity classification model\n"
            "biobank_model_sedentary_mins | mins | Total minutes spent in sedentary based on UKBB's "
            "pretrained activity classification model\n"
            "biobank_model_light_mins | mins | Total minutes spent in light activity based on UKBB's "
            "pretrained activity classification model\n"
            "biobank_sleep_mins | mins | Total minutes spent in sleep based on UKBB's pretrained "
            "activity classification model\n"
            "biobank_wearing_detection_mins | mins | Total minutes of coverage based on UKBB's "
            "imputed value\n"
            "emd_step_count | steps | Total steps based on the empirical mode decomposition technique\n"
            "ggir_wearing_detection_mins | mins | Total minutes of wearing based on GGIR's long epoch "
            "file where nonwearscore <=1 and clippingscore=0\n"
            "\n"
            "Chunked endpoints:\n\n"
            "Endpoint | Unit | Description\n"
            "--- | --- | ---\n"
            "interdaily_stability | IS | The consistency of the 24-hour rhythm across multiple "
            "days—how well activity follows the same pattern each day\n"
            "intradaily_variability | IV | The degree of fragmentation in the 24-hour activity "
            "rhythm—how much someone switches between rest and activity across the day"
        ),
    },
    {
        "patient_id": "Q2",
        "context": "",
        "input": "Summarize the number of subjects in each treatment cohort for CYAB.",
        "expected_output": (
            "Cohort Summary:\n\n"
            "Treatment cohort | Number of subjects\n"
            "--- | ---\n"
            "LY 30mg | 113\n"
            "LY 150mg | 112\n"
            "LY 450mg | 111\n"
            "Placebo | 222"
        ),
    },
    {
        "patient_id": "Q3",
        "context": "",
        "input": "For CYAB, identify the top 5 subjects with the highest compliance for each visit.",
        "expected_output": (
            "Baseline:\n\n"
            "Rank | Subject | Average wearing minutes\n"
            "--- | --- | ---\n"
            "1 | 10994 | 1376.88\n"
            "2 | 11005 | 1371.61\n"
            "3 | 11116 | 1370.71\n"
            "4 | 11148 | 1363.14\n"
            "5 | 10895 | 1361.27\n"
            "\n"
            "Visit 7:\n\n"
            "Rank | Subject | Average wearing minutes\n"
            "--- | --- | ---\n"
            "1 | 11116 | 1396.95\n"
            "2 | 11192 | 1393.54\n"
            "3 | 11210 | 1386.27\n"
            "4 | 10916 | 1383.77\n"
            "5 | 11174 | 1383.68\n"
            "\n"
            "Visit 9:\n\n"
            "Rank | Subject | Average wearing minutes\n"
            "--- | --- | ---\n"
            "1 | 10980 | 1393.36\n"
            "2 | 11107 | 1377.50\n"
            "3 | 11042 | 1371.21\n"
            "4 | 11084 | 1370.18\n"
            "5 | 10966 | 1369.61"
        ),
    },
    {
        "patient_id": "Q4",
        "context": "",
        "input": (
            "Provide summary statistics for daily step count in CYAB, and list top 10 records "
            "with the highest step count."
        ),
        "expected_output": (
            "Summary Statistics:\n\n"
            "Metric | Value\n"
            "--- | ---\n"
            "Record count | 9511\n"
            "Distinct subjects | 474\n"
            "Mean daily step count | 3328.75\n"
            "Standard deviation | 3872.18\n"
            "Minimum | 0\n"
            "25th percentile | 88.50\n"
            "Median | 1982.00\n"
            "75th percentile | 5316.50\n"
            "Maximum | 27118\n"
            "\n"
            "Top 10 records with highest daily step count:\n\n"
            "Rank | Subject | Date | Step count\n"
            "--- | --- | --- | ---\n"
            "1 | 10429 | 2025-03-23 | 27118\n"
            "2 | 10462 | 2025-05-10 | 26061\n"
            "3 | 10066 | 2024-10-31 | 25794\n"
            "4 | 10462 | 2025-06-07 | 24487\n"
            "5 | 10410 | 2025-04-22 | 24368\n"
            "6 | 10066 | 2024-10-20 | 24260\n"
            "7 | 10410 | 2025-04-20 | 24174\n"
            "8 | 11022 | 2025-10-25 | 23934\n"
            "9 | 10066 | 2024-11-03 | 23553\n"
            "10 | 10410 | 2025-02-22 | 23487"
        ),
    },
    {
        "patient_id": "Q5",
        "context": "",
        "input": (
            "Plot all sleep records and label abnormal sleep windows for subject 11169 in "
            "CYAB study."
        ),
        "expected_output": (
            "- Subject: 11169\n"
            "- Records: 24 subject-day sleep records\n"
            "- Date range: 2025-08-19 through 2025-09-18\n"
            "- Abnormality criteria: sleep window duration < 3.0 hours OR > 16.0 hours OR "
            "night overlap < 50%\n"
            "\n"
            "Plot description: a horizontal timeline chart titled \"Sleep Audit (Fixed "
            "Threshold) — 11169\", with one horizontal bar per sleep record plotted against "
            "clock hour (x-axis, 12:00 through the next day's 12:00) and sleep date (y-axis, "
            "2025-08-19 through 2025-09-18). Bars are colored blue for normal sleep windows "
            "and red for abnormal ones per the stated criteria, each annotated with its sleep "
            "efficiency percentage. Most normal (blue) nights run roughly 23:00-07:00 with "
            "80-88% efficiency; abnormal (red) nights are shorter, irregularly timed daytime "
            "or fragmented windows (e.g. a few minutes on 2025-08-27, or 13% efficiency on "
            "2025-09-09), consistent with the stated abnormality thresholds."
        ),
    },
    {
        "patient_id": "Q6",
        "context": "",
        "input": (
            "Plot change from baseline for the digital endpoints with error bars for study CYAB."
        ),
        "expected_output": (
            "Plot description: a grid of five line charts titled \"Change from Baseline in "
            "Actigraphy Endpoints\", one per endpoint — average 24-hour moderate/vigorous "
            "physical activity, average 24-hour step count, average daily acceleration "
            "magnitude in the most active 10-hour period, average nightly duration awake after "
            "falling asleep, and average nightly sleep duration during the sleep window. Each "
            "chart plots mean change from Baseline (y-axis) across Baseline, Visit 7, and "
            "Visit 9 (x-axis) as one line per treatment group (Placebo, LY 150mg, LY 30mg, "
            "LY 450mg), with vertical error bars showing variability at each visit. All series "
            "start at 0 at Baseline by definition. LY 30mg trends most positive on activity, "
            "step count, and acceleration magnitude by Visit 9, while LY 150mg trends most "
            "negative on those same endpoints. For sleep duration, LY 30mg shows the largest "
            "decline from baseline by Visit 9, while Placebo is roughly flat to slightly "
            "positive."
        ),
    },
    {
        "patient_id": "Q7",
        "context": "",
        "input": (
            "How is sleep duration changed from baseline across different treatment groups "
            "in study CYAB?"
        ),
        "expected_output": (
            "At Visit 7, the mean change in sleep duration was positive for LY 150mg, slightly "
            "negative for Placebo, more negative for LY 450mg, and most negative for LY 30mg.\n\n"
            "At Visit 9, Placebo shifted to a small positive change, while LY 150mg, LY 450mg, "
            "and especially LY 30mg remained below baseline on average."
        ),
    },
    {
        "patient_id": "Q8",
        "context": "",
        "input": (
            "Compare the average step count between baseline and visit 9 in LY 450 mg group."
        ),
        "expected_output": (
            "Baseline mean step count = 4544.50 steps\n"
            "Visit 9 mean step count = 4170.16 steps\n"
            "Absolute difference (Visit 9 - Baseline) = -374.34 steps\n"
            "Percent change = -8.24%\n"
            "Direction: Visit 9 is lower than Baseline."
        ),
    },
    {
        "patient_id": "Q9",
        "context": "",
        "input": "Count the number of subjects with actigraphy data at each visit in study CYAB.",
        "expected_output": (
            "Subjects with actigraphy data by visit:\n\n"
            "Visit | Number of subjects with actigraphy data\n"
            "--- | ---\n"
            "Baseline | 276\n"
            "Visit 7 | 127\n"
            "Visit 9 | 118"
        ),
    },
    {
        "patient_id": "Q10",
        "context": "",
        "input": "Summarize variability of step count in baseline for subject 11104 of study CYAB.",
        "expected_output": (
            "Subject 11104 had 14 baseline daily step-count records.\n\n"
            "The mean baseline daily step count was 5158.71 steps.\n\n"
            "The standard deviation was 2114.26 steps, indicating substantial day-to-day "
            "variability.\n\n"
            "The coefficient of variation was 40.98%, which suggests relatively high "
            "variability compared with the subject's own average step count.\n\n"
            "Daily step counts ranged from 2605.00 to 8402.00 steps during baseline."
        ),
    },
]
