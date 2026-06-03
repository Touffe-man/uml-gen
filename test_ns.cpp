namespace Hardware {
    class Moteur {
    public:
        int vitesse;
        void demarrer();
    };
}

namespace Control {
    class Robot {
    public:
        Hardware::Moteur moteur;
        void avancer();
    };
}