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
