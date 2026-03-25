# Herald — Regulatory Position

## Classification

Herald is a **knowledge management tool**, not a medical device. It extracts, structures, and queries existing clinical guideline content — it does not generate new clinical recommendations, interpret patient data from medical devices, or make autonomous treatment decisions.

## Regulatory Framework Analysis

### United States (FDA)

Under the 21st Century Cures Act, Clinical Decision Support (CDS) software is exempt from FDA regulation when **all four criteria** are met:

1. **Not intended to acquire, process, or analyse a medical image or signal** — Herald processes text documents, not medical data. ✓
2. **Intended for displaying, analysing, or printing medical information** — Herald displays existing guideline recommendations. ✓
3. **Intended for use by a healthcare professional** — Herald's output is for clinician use. ✓
4. **Intended to enable the healthcare professional to independently review the basis for recommendations** — Herald's source citations (section, page, exact text) enable independent verification. ✓

Herald meets all four Cures Act exemption criteria. However, if Herald is deployed as part of a system that takes automated clinical actions without clinician review, that system may require FDA clearance.

### European Union (MDR 2017/745)

Under MDR, software is a medical device if it is intended to be used for diagnosis, prevention, monitoring, prediction, prognosis, treatment, or alleviation of disease. CDS software that merely retrieves and presents existing clinical knowledge is generally not classified as a medical device.

Herald's function — structuring and querying published guideline text — is analogous to a clinical reference tool (like UpToDate or BMJ Best Practice), which are not classified as medical devices under MDR.

**However:** If Herald is integrated into a workflow where its output directly drives prescribing or treatment decisions without clinician review, it may fall within the scope of MDR Class IIa. Implementers should conduct their own conformity assessment.

### United Kingdom (MHRA)

The MHRA's guidance on standalone software as a medical device aligns with MDR. Herald's function as a guideline reference tool places it outside medical device classification, provided it does not process individual patient data from medical devices.

## Disclaimers

Herald ships with the following disclaimer in its README and CLI output:

> Herald is a research and reference tool. It extracts and structures existing clinical guideline content but does not replace clinical judgement. All recommendations should be verified against the source guideline before clinical use. Herald is not a medical device and has not been cleared or approved by any regulatory authority for clinical use.

## Responsibilities

| Party | Responsibility |
|---|---|
| **Herald maintainers** | Accuracy of the extraction engine. Clear documentation of limitations. |
| **Guideline authors** | Accuracy of the source clinical content. Licensing terms. |
| **Implementers** | Regulatory compliance in their jurisdiction. Clinical safety validation. User training. |
| **Clinicians** | Independent verification of recommendations. Clinical judgement. |

## Guideline Licensing

Herald (the tool) is MIT-licensed. However, parsed guideline JSONs inherit the licence of their source guideline:

- WHO guidelines: CC BY-NC-SA 3.0 IGO
- NICE guidelines: Open Government Licence (requires separate AI licence for some uses)
- APA/AMA guidelines: Proprietary — may not be redistributed

Herald records the source guideline's licence in the `guideline.licence` field of each parsed JSON. Users are responsible for complying with the source guideline's terms.

## Contact

For regulatory questions about Herald deployments, contact the implementing organisation's regulatory affairs team. Herald maintainers can provide technical documentation to support regulatory submissions.
