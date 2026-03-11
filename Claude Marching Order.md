
Last Modified by: Sean
Date 2/4/26
Claude Status: 

I received some initial user feedback in the last couple of days and would like to get some updates planned out and put in the implementation plan. Please review the below requests, ask any clarifying questions you are curious about, update our implementation plan, and provide me an assessment of what we should start working on next. I will prioritize the feedback updates into categories. 
Can we classify the current version of the product, as it stands now, as MVP 1.0. Updates for high and medium priorities will represent iterations to MVP 1. We will start MVP 2 after completing the current implementation plan and incorporated user feedback classified for MVP 1 implementation. For MVP 2 requirements, begin preparing an implementation plan and list of clarifying questions from you and to-dos for me in an MVP 2.0 planning document. 
	1. High priority feedback: items that should be incorporated ASAP before moving onto other items in the original implementation plan. 
		1. Planning team feedback
			1. The first blast time on each shift should be 5:30, not 5:20. 
			2. When possible, the same rubber type should not be scheduled back to back. i.e. alternate between XE and HR, unless no options are available to do so. 
				1. Flag this rule: I want to flag certain rules to review later. This decision, I feel, may not ultimately matter. I think it is a preference that if adhered to, could be to the detriment of the planning system. However, I want to incorporate it to encourage user uptake. Can you create a file in the root describing the planning algorithm's logic? Flag this as a rule for future review. Other rules we add may or may not be flagged in the same manner. 
			3. Eliminate the Pegging Report from the process
				1. Remove it as a requirement for upload, remove the "Actual Start Date" noted on the master schedule, and any other fields derived from the pegging report. I think it is just that field, but please provide a list of impacts from this change for review before implementation. 
		2. Customer service team feedback
			1. on the schedule page of the site add filtering capability, along with the sorting ability on each column. leave the current search box functionality as-is. 
			2. Add a column with the "Serial Number", pulled from the Open Sales Report, on the site's schedule page, as well as "Master Schedule" and "Impact Analysis" reports.
		3. My feedback
			1. On the header of the site, next to the "EstradaBot" title, please include the version and last update date, the updates we are working on now are for version MVP 1.1, use the date these changes are made for the update date. Can a rule be made to ensure this rev change and date are captured for each version change? 
				1. Create a page describing changes made in each revision, add a link to it at the bottom of the left menu bar called "Update Log". 
			2. Create a user feedback form and put it at the top of the update log page. Add a link to the main navigation for user feedback. It will go to the same page as the Update Log link in the nav bar, but that is okay by me. Have the user feedback stored on the cloud server. We will download feedback to incorporate in future sessions. If you can think of a workflow to make that easy, please implement it. 
			3. For security, I want to scrub some data from uploaded reports to prevent their storage on the site. Please scrub the "Unit Price" and "Customer Address" columns on any uploaded Open Sales reports.
			4. I want to incorporate the ability for the user to select different schedule mode outputs when viewing the schedule page dashboard. Can the schedule be simulated for multiple options and allow the user to switch between them with an interface that sits between the top summary boxes and the schedule table below? The option should allow the user to select between a 4 or 5 day work week. Future customizations to the work schedule will come in MVP 2
			5. We need to define the user groups responsibilities. I want the only generated schedule that is saved to the schedule page/dashboard to be that of what is uploaded by the planner. This will be the "Published Schedule". 
	2. Medium priority: Work into the current implementation plan as upgrades to MVP 1.
		1. My feedback: Create a list of all data fields used from the uploaded reports. I will attempt to create a custom report or link to live feeds with only the needed data for MVP 2.0. 
	3. Low priority: reserve for MVP 2.0 
		1. Customer Service feedback: 
			1. Add "Days Idle as" a column between the "Turnaround" and "Status" column on the schedule page. To define "Days Idle" on the main schedule page. This will require I provide you with an extra data field for the "Last Move Date". Please add this to the to-do list in the MVP 2.0 plan. 
		2. My feedback: 
			1. In MVP 2, I want to let the users simulate more scheduling options. 
				1. 4, 5, or 6 day work week
				2. 10 or 12 hour shifts
				3. A combination of the above with the ability to add "Skeleton shifts", where minimal crew is brought in to run a partial schedule of constrained cores. 
			2. Replace the core mapping excel upload with a database that can be manipulated by users with the correct rights. 
			3. Add features to allow for the planner to modify the schedule via a GUI on the site (dragging orders up/down, individually reprioritize specific orders, etc). Only the planner should have the ability to lock these changes in, though other users should be able to do 
			4. We need to define the user groups responsibilities/rights.
				1. Planner role:
					1. Sets and defines the published schedule. The file the planner uploads is used to generate schedule simulations. After a review of which schedule mode to choose, and which hot list items to approve, a master schedule will be published that appears on the "Schedule" page as the published Schedule.
					2. Reviews hot list and engineering order requests. Approves prioritization and sequencing of orders.
					3. Publishes the master schedule to be viewed by other user groups. 
				2. Customer Service role:
					1. Can view the schedule
					2. Can make hotlist requests and simulate impact/download impact report. 
					3. Can request and simulate setting a priority customer to override FIFO. 
				3. Manufacturing Engineering:
					1. Can manipulate the Core Mapping database. 
					2. Can request prioritization or creation of engineering work orders, which only appear on shop dispatch report. 
				4. Other roles: 
					1. TBD