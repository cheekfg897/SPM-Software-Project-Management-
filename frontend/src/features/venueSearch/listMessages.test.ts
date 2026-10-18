import { listMessages } from './listMessages'

describe('SCRUM-35 listMessages', () => {
  it("gives the list's own messages, then each item's, numbered from 1", () => {
    const fieldErrors = {
      required_facilities: ['At most 9 items are allowed.'],
      'required_facilities.1': ['Items cannot contain ",".'],
      'required_facilities.3': ['Items must be at most 50 characters.', 'Another.'],
      'required_accessibility.0': ['Items cannot be blank.'],
      min_capacity: ['min_capacity must be a positive number.'],
    }

    expect(listMessages(fieldErrors, 'required_facilities')).toEqual([
      'At most 9 items are allowed.',
      'Item 2: Items cannot contain ",".',
      'Item 4: Items must be at most 50 characters.',
      'Item 4: Another.',
    ])
  })

  it('gives nothing for a list the backend did not mention', () => {
    expect(listMessages({ 'required_facilities.0': ['Bad.'] }, 'required_accessibility')).toEqual(
      [],
    )
  })
})
