use crate::types::LogTemplate;
use uuid::Uuid;

pub fn build_template(normalized: String) -> LogTemplate {
    LogTemplate {
        id: Uuid::new_v4(),
        template: normalized,
    }
}
