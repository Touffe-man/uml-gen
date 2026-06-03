class Vehicule {
public:
    int vitesse;
    void bouger();
};

class Voiture : public Vehicule {
public:
    int nbRoues;
    void klaxonner();
};