# Catalog Dataset

## Overview
This folder contains PDFs of the Undergraduate and Academic Academic Catalog for the 2026-2027 academic year. As the catalog-scraper has been discontinued due to an AWS WAF challenge, I had to produce a different means of acquiring such data. For this plan, I will choose to use Microsoft: Print to PDF all pages of the catalog.

## Requirements to Replicate
Windows 10/11 OS.

## Steps

1. Go to Course Descriptions. This can be accessed via `https://catalog.charlotte.edu/` > 2026-2027 Undergraduate/Graduate Catalog > Course Descriptions.
2. On the right of the title `Course Descriptions` there is a print icon. Click it to pull a popup.
3. Click `Expand All Courses`.
4. Click `Print this Page`
5. Ensure the destination is `Microsoft Print to PDF`.
6. Click Print.

## IMPORTANT
All the syntax must follow this pattern: <UNDERGRADUATE/GRADUATE_Catalog>_<ACADEMIC-YEAR>_<pg#>. Such as `Undergraduate_Catalog_2026-2027_pg1` or `Graduate_Catalog_2026-2027_pg2`. Deviations are not allowed.

The operation `Microsoft Print to PDF` follows these parameters:
- Orientation: Portrait
- Pages: All
- Color mode: Color (greyed out due to no printer)
- Paper size: Letter
- Scale: Fit to page width
- Pages per sheet: 1
- Margins: Default
- Options: Print headers and footers
    - Note about the options: Prefabably without any headers or footers, but I forgot to disable them and later noticed about 38 entries in and I am not keen to spend an hour to save to PDF again.
