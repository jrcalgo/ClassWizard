# Catalog Dataset

## Overview
This folder contains the main tool for the catalog pipeline tool, as well as the PDFs that it was tested on. These directions are to allow the developer to replicate the input as Reshlynt made it. Directions for the catalog_pipeline are found by unzipping the file and looking at the README.

## Requirements to Replicate
Windows 10/11 OS.

## Steps to gather vaild PDFs for this tool

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

# Docker Usage
## Catalog Pipeline Setup
- Unzip the file at the ROOT of the repository for this tool to work. Ensure that the name of the folder is called `catalog_pipeline`. It may seem confusing that there will be two folders, one in the other, called `catalog_pipeline` but I do not suggest to change it.


- If you want to use Docker as the means to pipe catalog PDFs into output, you **must** put your PDFs in `data/catalog_pdfs`.