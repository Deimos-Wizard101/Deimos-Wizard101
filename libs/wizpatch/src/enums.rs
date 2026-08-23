#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Game {
    Wizard101,
    Pirate101,
}

impl Game {
    pub fn domain(self) -> &'static str {
        match self {
            Game::Wizard101 => "wizard101.com",
            Game::Pirate101 => "pirate101.com",
        }
    }

    pub fn host(self, country: Country) -> String {
        format!("patch.{}.{}", country.code(), self.domain())
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Country {
    Us,
    Eu,
}

impl Country {
    pub fn code(self) -> &'static str {
        match self {
            Country::Us => "us",
            Country::Eu => "eu",
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Platform {
    Windows,
    MacOs,
    Steam,
}

impl Platform {
    pub fn port(self) -> u16 {
        match self {
            Platform::Windows => 12500,
            Platform::MacOs => 12600,
            Platform::Steam => 12700,
        }
    }
}
