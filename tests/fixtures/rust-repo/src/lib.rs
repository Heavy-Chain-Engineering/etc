pub fn greet(name: &str) -> String {
    format!("Hi {}", name)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn greet_returns_hello() {
        assert_eq!(greet("World"), "Hi World");
    }
}
