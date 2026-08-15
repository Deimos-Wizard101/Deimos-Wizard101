//! Tiny glob matcher for file-list selection. No external deps.
//!
//! A pattern with no wildcard is treated as a case-insensitive *substring*
//! match, so `Root.wad` selects any path containing it. A pattern containing
//! `*` or `?` is matched as a glob, where `*` matches any run of characters
//! (including `/`) and `?` matches exactly one. Matching is case-insensitive
//! because patch paths mix cases across platforms.

/// True if `name` matches any of `patterns`. An empty list matches nothing;
/// callers treat "no patterns" as "match everything" before calling here.
pub fn matches_any(name: &str, patterns: &[String]) -> bool {
    patterns.iter().any(|p| matches(name, p))
}

/// Match a single pattern against `name`.
pub fn matches(name: &str, pattern: &str) -> bool {
    let name = name.to_ascii_lowercase();
    let pattern = pattern.to_ascii_lowercase();
    if pattern.contains('*') || pattern.contains('?') {
        glob_match(name.as_bytes(), pattern.as_bytes())
    } else {
        name.contains(&pattern)
    }
}

/// Classic linear wildcard match with `*` backtracking. `*` spans any bytes
/// (including `/`); `?` matches one byte.
fn glob_match(text: &[u8], pat: &[u8]) -> bool {
    let (mut ti, mut pi) = (0usize, 0usize);
    // Remembered backtrack point: (pattern index just past a `*`, text index).
    let mut star: Option<(usize, usize)> = None;

    while ti < text.len() {
        if pi < pat.len() && (pat[pi] == b'?' || pat[pi] == text[ti]) {
            ti += 1;
            pi += 1;
        } else if pi < pat.len() && pat[pi] == b'*' {
            star = Some((pi + 1, ti));
            pi += 1;
        } else if let Some((resume_pi, resume_ti)) = star {
            // The `*` swallows one more text byte and we retry.
            pi = resume_pi;
            ti = resume_ti + 1;
            star = Some((resume_pi, ti));
        } else {
            return false;
        }
    }
    // Trailing `*`s in the pattern are free to match empty.
    while pi < pat.len() && pat[pi] == b'*' {
        pi += 1;
    }
    pi == pat.len()
}

#[cfg(test)]
mod tests {
    use super::matches;

    #[test]
    fn substring_when_no_wildcard() {
        assert!(matches("Data/GameData/Root.wad", "root.wad"));
        assert!(matches("Data/GameData/Root.wad", "GameData"));
        assert!(!matches("Data/GameData/Root.wad", "Mob.wad"));
    }

    #[test]
    fn star_spans_slashes() {
        assert!(matches("Data/GameData/Root.wad", "*.wad"));
        assert!(matches("Data/GameData/Root.wad", "Data/*Root.wad"));
        assert!(matches("Data/GameData/Root.wad", "data/*"));
        assert!(!matches("Data/GameData/Root.dat", "*.wad"));
    }

    #[test]
    fn question_matches_one() {
        assert!(matches("Mob-01.wad", "Mob-??.wad"));
        assert!(!matches("Mob-1.wad", "Mob-??.wad"));
    }
}
