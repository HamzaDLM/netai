use dashmap::DashSet;

pub struct TemplateDeduplicator {
    seen: DashSet<String>,
}

impl TemplateDeduplicator {
    pub fn new() -> Self {
        Self {
            seen: DashSet::new(),
        }
    }

    pub fn is_new(&self, template: &str) -> bool {
        self.seen.insert(template.to_string())
    }

    pub fn mark_seen(&self, template: String) {
        self.seen.insert(template);
    }

    pub fn len(&self) -> usize {
        self.seen.len()
    }
}

#[cfg(test)]
mod tests {
    use super::TemplateDeduplicator;

    #[test]
    fn tracks_first_seen_template() {
        let dedup = TemplateDeduplicator::new();
        assert!(dedup.is_new("vendor::template-a"));
        assert!(!dedup.is_new("vendor::template-a"));
    }

    #[test]
    fn mark_seen_preloads_key() {
        let dedup = TemplateDeduplicator::new();
        dedup.mark_seen("vendor::template-b".to_string());
        assert!(!dedup.is_new("vendor::template-b"));
        assert_eq!(dedup.len(), 1);
    }
}
