// Reading a number out of a text input, where blank is not zero.
//
// Three different wrong answers are avoided here, and each one was the reason
// one of this function's four former copies existed:
//
// * Number('') is 0. For a nullable field a blank box means "not recorded",
//   which is a different claim from "zero grams" or "zero centimetres tall".
// * Number('abc') and Number('1e999') are NaN, and NaN passes a `> 0` check by
//   being false rather than by throwing. Left as NaN it serialises to null in
//   the request body, so a meal saves with a macro silently missing.
// * Number(' 12 ') is 12, so trimming first is what separates "nothing typed"
//   from "typed something that is not a number". Both return null, but only
//   after the blank case has been ruled out.
//
// The goal fields in Settings deliberately still use a bare Number(): they are
// NOT NULL columns with a real default, so there is no null to represent.
export const num = (value: string) => {
  if (value.trim() === '') return null
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : null
}
