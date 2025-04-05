typedef struct {
    int mass;
    int volume;
    float density;
    float capacity[2];
} paramFull;

typedef struct {
    int id;
    float totalmass;
    paramFull mainFull;
    paramFull subFull;
    paramFull otherFull[2];
} unit;
