
#include <list>
#include <string>

using math_history = std::pair<std::string, float>;

using namespace foo::bar;

namespace mymath
{

class Foo()
{
public:
    float boo();
}

/*
    Fun calculator class for example purposes
*/
class FloatCalculator
{

    FloatCalculator();
    ~FloatCalculator();

    float mult(float a, float b = 0);
    float div(float a, float b);
    float add(float a, float b);
    float sub(float a, float b);

private:

    std::list<math_history> m_history;

    float m_secretValue;

};

} // namespace mymath