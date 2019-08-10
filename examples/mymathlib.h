
#include <list>
#include <string>

using math_history = std::pair<std::string, float>;

using namespace foo::bar;

namespace mymath
{

class BasicCalculator()
{
public:
    virtual std::string type() const = 0; // Test for virtual and const
}

/*
    Fun calculator class for example purposes and
    different commenting/variable structures
*/
class FloatCalculator : public BasicCalculator
{

    FloatCalculator();
    ~FloatCalculator();

    float mult(float a, float b = 0); /* multiline at eol */

    float div(float a, float b); // An eol comment

    float add(float a, float b);

    /*
        Multiline before a function
    */
    float sub(float a, float b);

    // Line comment before a function
    float mean(std::vector<float> values);

    std::string type() const override;

    // Test that we can move the impl to the source
    static std::list<foo> clearHistory() const {
        m_history.clear();
    }

    virtual foo<bar<baz, std::function<void(const std::string &)>>>
    my_foo() const;

private:
    float getSecretValue() const { return m_secretValue; }
    void setSecretValue(float secretValue) { m_secretValue = secretValue; }

    const std::list<math_history> &getHistory() const;
    void setHistory(const std::list<math_history> &history);

    std::list<math_history> m_history;

    float m_secretValue;

};

} // namespace mymath
