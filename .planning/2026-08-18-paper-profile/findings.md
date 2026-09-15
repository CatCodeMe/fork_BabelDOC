# Findings

- `translate-chunks.zsh` remains the active long-document Skill entry; `translate-book.zsh` is a legacy short-document wrapper.
- The SSD paper is 19 pages. Its bibliography uses two narrow source columns; translating each source box independently leaves too little width for full URLs.
- The math font `txmiaX` is not recognized by `is_formulas_font`, reproducing the formula-protection defect.
- The requested profile must remain opt-in so book layout behavior is unchanged.
