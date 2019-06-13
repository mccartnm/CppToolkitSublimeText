
#include <list>
#include <string>

using math_history = std::pair<std::string, float>;

using namespace foo::bar;

namespace mymath
{

/*
    Fun calculator class for example purposes
*/
class FloatCalculator
{
public:

    FloatCalculator();
    ~FloatCalculator();

    float mult(float a, float b = 0);
    float div(float a, float b);
    float add(float a, float b);
    float sub(float a, float b);

    // Example for converting camel to snake
    const std::list<math_history> &getHistory() const;

private:

    std::list<math_history> m_history;

};

} // namespace mymath