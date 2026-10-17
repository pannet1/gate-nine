
stake holders: murugan alias murugesan is the chief architect of rachis.co.in .. the lead 
developer is jashveer. karthick is me the tester doing the tests.


aim of the project: 
We  want to do the final functional testing on https://rachis.co.in before delivering to the customer.
this is done by AI models but is expected to be done 100% human.



every test is stored in a unique folder (suggest naming scheme here).
the structure is same for all these unique folders.


murugan or jashveer: input md file from 
ai: convert it into test case. we may traverse the same path again and again till 
the testing document is finalized. it will be overwritten several times till the 
correct test data is arrived. the human in the loop should be able to correct 
the test data as it is getting prepared.

karthick: runs the ai prepared test on rachis, so that the test will have one 
final result. pass or fail.

=== test ===
if the submitted form passes through,  the screen shot is kept for reference. 
if form submission fails with error message, a new screenshot is taken and overwrites the previous one.
this way we have only the one screenshot per document.

if a test fails, developers are notified immediately, so that they can fix. the testing is stalled 
if all tests pass, the developers are notified and new features are awaited.


=== log ===
we want to log all the activities
operation <name:value> <form name> 
examples:

input product:hamam voucher
create screenshot voucher
save screenshot voucher
delete screenshot voucher
click home  delivery note

we are just following operation on document naming scheme

we want to have live relay of the log on what operation is being currently done.
this way murugesan and jashveer will have real time updates on what is going on.


=== infra ===
we want to remote server for developers to see live log.
we also want to use the remote compute where possible
the remote is terminal only, so we need to find a way to run the tests
and see the browsers being opened up and fields entered.

we will have webserver running alongwith the log, this will display the test files in a rich html interface
where possible, the screenshot, the input document, the ai prepared test, etc.





