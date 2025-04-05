typedef struct {
    int mass;
    int volume;
} param;

typedef struct {
    int id;
    param main;
    param sub;
    param other[2];	
} unit;
